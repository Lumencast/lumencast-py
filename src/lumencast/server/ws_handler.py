"""WebSocket connection handler implementing the LSDP/1 lifecycle."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

try:
    from fastapi import WebSocket
except ImportError as _e:  # pragma: no cover
    msg = 'lumencast.server.ws_handler requires the [server] extra: pip install "lumencast[server]"'
    raise ImportError(msg) from _e

from lumencast.protocol.codec import (
    DecodeError,
    UnknownTypeError,
    VersionMismatchError,
    decode_client,
    encode,
)
from lumencast.protocol.envelope import SUBPROTOCOLS
from lumencast.protocol.errors import ErrorCode
from lumencast.protocol.frames import Cause, Error, Input, Ping, Pong, Subscribe, Unsubscribe
from lumencast.protocol.types import Role
from lumencast.server.auth import AuthError
from lumencast.server.scene import Scene, Subscription

if TYPE_CHECKING:
    from lumencast.server.server import Server

_log = logging.getLogger("lumencast.server.ws")

# WebSocket close codes used in this module — match RFC 6455.
WS_CLOSE_NORMAL = 1000
WS_CLOSE_PROTOCOL_ERROR = 1002
WS_CLOSE_POLICY_VIOLATION = 1008

SUBSCRIBE_TIMEOUT_SECS = 30.0
PING_INTERVAL_SECS = 30.0


async def handle_ws(server: Server, ws: WebSocket) -> None:
    """Run one LSDP/1 WebSocket session against ``ws``.

    Lifecycle :

    1. Negotiate ``Sec-WebSocket-Protocol = lsdp.v1``.
    2. Accept the upgrade.
    3. Read the first ``Subscribe`` frame within ``SUBSCRIBE_TIMEOUT_SECS``.
    4. Authenticate ; resolve scene ; emit Snapshot.
    5. Run reader + writer until either side errors.
    """
    # The LSDP/1 § 1 contract requires the client to advertise either
    # lsdp.v1 or lsdp.v1.1 in Sec-WebSocket-Protocol. We prefer 1.1 when
    # both are offered, fall back to 1.0 otherwise. Some ASGI backends do
    # not populate ``scope["subprotocols"]`` when the legacy websockets
    # backend is in play, so we also fall back to inspecting the raw header.
    requested_protocols = _requested_subprotocols(ws)
    chosen: str | None = None
    for candidate in SUBPROTOCOLS:  # 1.1 preferred, 1.0 fallback
        if candidate in requested_protocols:
            chosen = candidate
            break
    if chosen is None:
        await ws.accept()
        await ws.close(
            code=WS_CLOSE_POLICY_VIOLATION,
            reason="lsdp.v1 or lsdp.v1.1 subprotocol required",
        )
        return

    await ws.accept(subprotocol=chosen)

    try:
        sub_frame = await _read_subscribe(ws)
    except VersionMismatchError:
        # LSDP/1 § 13 : v != 1 → close 1002 without an error frame.
        await ws.close(code=WS_CLOSE_PROTOCOL_ERROR, reason="version mismatch")
        return
    except (TimeoutError, DecodeError, asyncio.CancelledError) as e:
        await _send_error(ws, 0, ErrorCode.AUTH_DENIED, str(e), recoverable=False)
        await ws.close(code=WS_CLOSE_POLICY_VIOLATION, reason="subscribe expected")
        return
    except Exception as e:
        await _send_error(ws, 0, ErrorCode.AUTH_DENIED, str(e), recoverable=False)
        await ws.close(code=WS_CLOSE_POLICY_VIOLATION, reason="subscribe expected")
        return

    try:
        identity = await server.auth.authenticate(sub_frame.token)
    except AuthError as e:
        await _send_error(ws, 0, ErrorCode.AUTH_DENIED, str(e), recoverable=False)
        await ws.close(code=WS_CLOSE_POLICY_VIOLATION, reason="auth denied")
        return
    if not identity.is_authenticated():
        await _send_error(ws, 0, ErrorCode.AUTH_DENIED, "token invalid", recoverable=False)
        await ws.close(code=WS_CLOSE_POLICY_VIOLATION, reason="auth denied")
        return

    scene, err_code, err_msg = server.resolve_scene(sub_frame, identity)
    if scene is None:
        assert err_code is not None
        await _send_error(ws, 0, err_code, err_msg, recoverable=False)
        await ws.close(code=WS_CLOSE_POLICY_VIOLATION, reason=err_msg)
        return

    live = sub_frame.scene == ""
    # LSDP/1.1 §4.1, §18 — honour since_sequence when the replay buffer
    # covers the gap. Otherwise fall back to a fresh snapshot at the
    # current scene seq.
    sub, snap, replay_records = await scene.subscribe_with_resume(
        live=live,
        since_sequence=sub_frame.since_sequence,
    )
    try:
        if snap is not None:
            await ws.send_text(encode(snap))
        else:
            from lumencast.protocol.frames import Delta as DeltaFrame  # local

            for r in replay_records:
                d = DeltaFrame(seq=r.seq, patches=list(r.patches), cause=r.cause)
                await ws.send_text(encode(d))
    except Exception as e:
        _log.debug("initial frame send failed: %s", e)
        await scene.unsubscribe(sub)
        return

    try:
        await _run_session(ws, scene, sub, identity)
    finally:
        await server.detach(sub)


def _requested_subprotocols(ws: WebSocket) -> list[str]:
    """Return the LSDP subprotocols the client advertised on the upgrade.

    Reads ``scope["subprotocols"]`` first (the ASGI standard) ; falls back
    to parsing ``Sec-WebSocket-Protocol`` from the raw header when the
    backend doesn't populate the scope key.
    """
    raw = list(ws.scope.get("subprotocols") or [])
    if raw:
        return raw
    try:
        header = ws.headers.get("sec-websocket-protocol", "")
    except Exception:
        header = ""
    if not header:
        return []
    return [s.strip() for s in header.split(",") if s.strip()]


async def _read_subscribe(ws: WebSocket) -> Subscribe:
    """Wait for and parse the first frame ; reject anything not Subscribe."""
    raw = await asyncio.wait_for(ws.receive_text(), timeout=SUBSCRIBE_TIMEOUT_SECS)
    msg = decode_client(raw)
    if not isinstance(msg, Subscribe):
        raise DecodeError("first frame must be subscribe")
    return msg


async def _run_session(
    ws: WebSocket,
    scene: Scene,
    sub: Subscription,
    identity: Any,
) -> None:
    """Reader and writer loops sharing the connection."""
    cancel_event = asyncio.Event()

    async def reader() -> None:
        try:
            while not cancel_event.is_set():
                raw = await ws.receive_text()
                try:
                    msg = decode_client(raw)
                except VersionMismatchError as e:
                    await _send_error(
                        ws,
                        scene.current_seq(),
                        ErrorCode.VERSION_MISMATCH,
                        str(e),
                        recoverable=False,
                    )
                    cancel_event.set()
                    return
                except (DecodeError, UnknownTypeError) as e:
                    await _send_error(
                        ws,
                        scene.current_seq(),
                        ErrorCode.INTERNAL,
                        str(e),
                        recoverable=False,
                    )
                    cancel_event.set()
                    return
                await _dispatch(ws, scene, sub, identity, msg)
        except Exception as e:
            _log.debug("reader ended: %s", e)
        finally:
            cancel_event.set()

    async def writer() -> None:
        try:
            while not cancel_event.is_set():
                try:
                    msg = await asyncio.wait_for(sub.queue.get(), timeout=PING_INTERVAL_SECS)
                except TimeoutError:
                    await ws.send_text(encode(Ping()))
                    continue
                if msg is None:
                    return
                await ws.send_text(encode(msg))
        except Exception as e:
            _log.debug("writer ended: %s", e)
        finally:
            cancel_event.set()

    await asyncio.gather(reader(), writer(), return_exceptions=True)


async def _dispatch(
    ws: WebSocket,
    scene: Scene,
    sub: Subscription,
    identity: Any,
    msg: Subscribe | Input | Ping | Pong | Unsubscribe,
) -> None:
    """Route a parsed client frame to its handler."""
    if isinstance(msg, Input):
        # LSDP/1.1 §4.2 — derive provenance for the resulting delta when
        # the input carries a client_msg_id. Threaded through to the
        # scene so the emitted delta can echo it as cause.input_id.
        cause = None
        if msg.client_msg_id is not None:
            subject = getattr(identity, "subject", None) or getattr(identity, "role", "operator")
            role = getattr(identity, "role", "operator")
            cause = Cause(source=f"{role}:{subject}", input_id=msg.client_msg_id)
        result = await scene.apply_input(identity, msg.patches, cause=cause)
        if result is not None:
            code_str, err_msg, err_path = result
            try:
                code = ErrorCode(code_str)
            except ValueError:
                code = ErrorCode.INTERNAL
            recoverable = code is not ErrorCode.AUTH_DENIED
            await _send_error(
                ws,
                scene.current_seq(),
                code,
                err_msg,
                recoverable=recoverable,
                path=err_path,
            )
        return
    if isinstance(msg, Ping):
        # LSDP/1.1 §3.5 — echo nonce verbatim if present.
        await ws.send_text(encode(Pong(nonce=msg.nonce)))
        return
    if isinstance(msg, Pong):
        # Liveness reply ; nothing to do.
        return
    if isinstance(msg, Unsubscribe):
        # LSDP/1.1 §4.4 — clean teardown. Close WS within 1s, no error.
        await ws.close(code=1000)
        return
    if isinstance(msg, Subscribe):
        await _send_error(
            ws,
            scene.current_seq(),
            ErrorCode.INTERNAL,
            "duplicate subscribe",
            recoverable=False,
        )


async def _send_error(
    ws: WebSocket,
    seq: int,
    code: ErrorCode,
    message: str,
    *,
    recoverable: bool,
    path: str | None = None,
) -> None:
    """Encode and ship one Error frame ; swallow send failures.

    ``path`` MUST be set on path-scoped error codes per LSDP/1.0.1 §3.4.1
    (``WRITE_FORBIDDEN``, ``UNKNOWN_PATH``, ``INVALID_VALUE``).
    """
    frame = Error(
        seq=seq,
        code=code.value,
        message=message,
        recoverable=recoverable,
        path=path,
    )
    try:
        await ws.send_text(encode(frame))
    except Exception as e:
        _log.debug("error send failed: %s", e)


# Re-exported for handler tests.
__all__ = ["Role", "handle_ws"]
