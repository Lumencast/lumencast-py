"""LSDP/1 encode / decode for typed frames.

The codec is the only piece of the SDK allowed to assemble or parse a
wire frame. Every other layer round-trips through these functions, which
keeps the byte-level conformance fixtures load-bearing.
"""

from __future__ import annotations

from typing import Any

from lumencast.protocol.envelope import VERSION, decode_json, encode_json
from lumencast.protocol.frames import (
    Cause,
    Delta,
    Error,
    Input,
    Patch,
    Ping,
    Pong,
    SceneChanged,
    SceneTransition,
    Snapshot,
    Subscribe,
    TransitionSpec,
    Unsubscribe,
)
from lumencast.protocol.types import (
    FRAME_DELTA,
    FRAME_ERROR,
    FRAME_INPUT,
    FRAME_PING,
    FRAME_PONG,
    FRAME_SCENE_CHANGED,
    FRAME_SNAPSHOT,
    FRAME_SUBSCRIBE,
    FRAME_UNSUBSCRIBE,
)


class DecodeError(ValueError):
    """Generic invalid envelope or frame body."""


class VersionMismatchError(DecodeError):
    """Envelope ``v`` field does not equal :data:`VERSION`."""


class UnknownTypeError(DecodeError):
    """Envelope ``type`` is not one of the recognised LSDP/1 frames."""


def encode(msg: object) -> str:
    """Serialise a typed frame to its canonical JSON text representation.

    The envelope ``v`` and ``type`` fields are stamped here ; callers
    construct frames with semantic fields only.

    Raises :class:`TypeError` if ``msg`` is not one of the LSDP/1 frame
    types defined in :mod:`lumencast.protocol.frames`.
    """
    obj = _frame_to_dict(msg)
    return encode_json(obj)


def decode_client(raw: str | bytes) -> Subscribe | Input | Ping | Pong | Unsubscribe:
    """Parse a client-emitted frame.

    Server use. Returns one of (:class:`Subscribe`, :class:`Input`,
    :class:`Ping`, :class:`Pong`, :class:`Unsubscribe`). Pong because clients
    may answer server-initiated pings ; Unsubscribe is the 1.1 clean
    teardown signal.
    """
    env = _parse_envelope(raw)
    t = env["type"]
    if t == FRAME_SUBSCRIBE:
        since = env.get("since_sequence")
        return Subscribe(
            token=env.get("token", ""),
            scene=env.get("scene", "") or "",
            session=env.get("session", "") or "",
            since_sequence=int(since) if since is not None else None,
        )
    if t == FRAME_INPUT:
        return Input(
            patches=_parse_patches(env.get("patches")),
            client_msg_id=env.get("client_msg_id"),
        )
    if t == FRAME_PING:
        return Ping(nonce=env.get("nonce"))
    if t == FRAME_PONG:
        return Pong(nonce=env.get("nonce"))
    if t == FRAME_UNSUBSCRIBE:
        return Unsubscribe()
    raise UnknownTypeError(f"protocol: unknown client frame type {t!r}")


def decode_server(raw: str | bytes) -> Snapshot | Delta | SceneChanged | Error | Pong | Ping:
    """Parse a server-emitted frame.

    Client / harness use. Returns one of (:class:`Snapshot`,
    :class:`Delta`, :class:`SceneChanged`, :class:`Error`, :class:`Pong`,
    :class:`Ping`).

    Per spec § 13, runtimes that receive an unknown frame type MUST
    silently ignore it ; this function surfaces the unknown via
    :class:`UnknownTypeError` so callers can choose.
    """
    env = _parse_envelope(raw)
    t = env["type"]
    if t == FRAME_SNAPSHOT:
        return Snapshot(
            seq=int(env.get("seq", 0)),
            ts=env.get("ts", "") or "",
            scene_id=env.get("scene_id", ""),
            scene_version=env.get("scene_version", ""),
            state=dict(env.get("state") or {}),
        )
    if t == FRAME_DELTA:
        return Delta(
            seq=int(env.get("seq", 0)),
            ts=env.get("ts", "") or "",
            patches=_parse_patches(env.get("patches")),
            cause=_parse_cause(env.get("cause")),
        )
    if t == FRAME_SCENE_CHANGED:
        return SceneChanged(
            seq=int(env.get("seq", 0)),
            ts=env.get("ts", "") or "",
            scene_id=env.get("scene_id", ""),
            scene_version=env.get("scene_version", ""),
            from_scene_id=env.get("from_scene_id"),
            transition=_parse_scene_transition(env.get("transition")),
        )
    if t == FRAME_ERROR:
        return Error(
            seq=int(env.get("seq", 0)),
            ts=env.get("ts", "") or "",
            code=env.get("code", ""),
            message=env.get("message", ""),
            recoverable=bool(env.get("recoverable", False)),
            retry_after_ms=int(env.get("retry_after_ms", 0) or 0),
            path=env.get("path"),
        )
    if t == FRAME_PONG:
        return Pong(nonce=env.get("nonce"))
    if t == FRAME_PING:
        return Ping(nonce=env.get("nonce"))
    raise UnknownTypeError(f"protocol: unknown server frame type {t!r}")


def _parse_envelope(raw: str | bytes) -> dict[str, Any]:
    """Decode JSON, validate ``v == 1``, return the envelope dict."""
    try:
        env = decode_json(raw)
    except ValueError as e:
        raise DecodeError(f"protocol: invalid JSON envelope: {e}") from e
    v = env.get("v")
    if v != VERSION:
        raise VersionMismatchError(f"protocol: envelope v mismatch, got v={v!r}")
    if "type" not in env or not isinstance(env["type"], str):
        raise DecodeError("protocol: envelope missing 'type'")
    return env


def _parse_patches(raw: Any) -> list[Patch]:
    """Validate and convert a raw patch list to typed :class:`Patch` records."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise DecodeError(f"protocol: patches must be a list, got {type(raw).__name__}")
    out: list[Patch] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise DecodeError(f"protocol: patch[{i}] must be an object")
        if "path" not in item:
            raise DecodeError(f"protocol: patch[{i}] missing 'path'")
        out.append(
            Patch(
                path=str(item["path"]),
                value=item.get("value"),
                transition=_parse_transition_spec(item.get("transition")),
            )
        )
    return out


def _parse_transition_spec(raw: Any) -> TransitionSpec | None:
    """LSDP/1.1 §3.2.2 — discriminated transition kinds."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise DecodeError("protocol: transition must be an object")
    kind = raw.get("kind")
    if kind not in ("tween", "spring", "snap"):
        raise DecodeError(f"protocol: transition.kind must be tween|spring|snap, got {kind!r}")
    spec = TransitionSpec(kind=kind)
    if "duration_ms" in raw:
        spec.duration_ms = int(raw["duration_ms"])
    if "easing" in raw:
        easing = raw["easing"]
        if easing not in ("linear", "ease-in", "ease-out", "ease-in-out"):
            raise DecodeError(f"protocol: transition.easing invalid: {easing!r}")
        spec.easing = easing
    if "stiffness" in raw:
        spec.stiffness = float(raw["stiffness"])
    if "damping" in raw:
        spec.damping = float(raw["damping"])
    return spec


def _parse_cause(raw: Any) -> Cause | None:
    """LSDP/1.1 §3.2.3 — provenance metadata."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise DecodeError("protocol: cause must be an object")
    source = raw.get("source")
    if not isinstance(source, str):
        raise DecodeError("protocol: cause.source must be a string")
    return Cause(source=source, input_id=raw.get("input_id"))


def _parse_scene_transition(raw: Any) -> SceneTransition | None:
    """LSDP/1.1 §3.3.1 — show-level scene transition."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise DecodeError("protocol: scene transition must be an object")
    kind = raw.get("kind")
    if not isinstance(kind, str):
        raise DecodeError("protocol: scene transition.kind must be a string")
    duration = raw.get("duration_ms")
    return SceneTransition(
        kind=kind,
        duration_ms=int(duration) if duration is not None else None,
    )


def _frame_to_dict(msg: object) -> dict[str, Any]:
    """Convert a typed frame to its on-wire dict shape."""
    if isinstance(msg, Snapshot):
        out: dict[str, Any] = {
            "v": VERSION,
            "type": FRAME_SNAPSHOT,
            "seq": msg.seq,
            "scene_id": msg.scene_id,
            "scene_version": msg.scene_version,
            "state": msg.state,
        }
        if msg.ts:
            out["ts"] = msg.ts
        return out
    if isinstance(msg, Delta):
        out = {
            "v": VERSION,
            "type": FRAME_DELTA,
            "seq": msg.seq,
            "patches": [_patch_to_dict(p) for p in msg.patches],
        }
        if msg.ts:
            out["ts"] = msg.ts
        if msg.cause is not None:
            out["cause"] = _cause_to_dict(msg.cause)
        return out
    if isinstance(msg, SceneChanged):
        out = {
            "v": VERSION,
            "type": FRAME_SCENE_CHANGED,
            "seq": msg.seq,
            "scene_id": msg.scene_id,
            "scene_version": msg.scene_version,
        }
        if msg.ts:
            out["ts"] = msg.ts
        if msg.from_scene_id:
            out["from_scene_id"] = msg.from_scene_id
        if msg.transition is not None:
            out["transition"] = _scene_transition_to_dict(msg.transition)
        return out
    if isinstance(msg, Error):
        out = {
            "v": VERSION,
            "type": FRAME_ERROR,
            "seq": msg.seq,
            "code": msg.code,
            "message": msg.message,
            "recoverable": msg.recoverable,
        }
        if msg.ts:
            out["ts"] = msg.ts
        if msg.retry_after_ms:
            out["retry_after_ms"] = msg.retry_after_ms
        if msg.path is not None:
            out["path"] = msg.path
        return out
    if isinstance(msg, Pong):
        out = {"v": VERSION, "type": FRAME_PONG}
        if msg.nonce is not None:
            out["nonce"] = msg.nonce
        return out
    if isinstance(msg, Ping):
        out = {"v": VERSION, "type": FRAME_PING}
        if msg.nonce is not None:
            out["nonce"] = msg.nonce
        return out
    if isinstance(msg, Unsubscribe):
        return {"v": VERSION, "type": FRAME_UNSUBSCRIBE}
    if isinstance(msg, Subscribe):
        out = {"v": VERSION, "type": FRAME_SUBSCRIBE, "token": msg.token}
        if msg.scene:
            out["scene"] = msg.scene
        if msg.session:
            out["session"] = msg.session
        if msg.since_sequence is not None:
            out["since_sequence"] = msg.since_sequence
        return out
    if isinstance(msg, Input):
        out = {
            "v": VERSION,
            "type": FRAME_INPUT,
            "patches": [_patch_to_dict(p) for p in msg.patches],
        }
        if msg.client_msg_id is not None:
            out["client_msg_id"] = msg.client_msg_id
        return out
    raise TypeError(f"protocol: cannot encode {type(msg).__name__}")


def _patch_to_dict(p: Patch) -> dict[str, Any]:
    out: dict[str, Any] = {"path": p.path, "value": p.value}
    if p.transition is not None:
        out["transition"] = _transition_spec_to_dict(p.transition)
    return out


def _transition_spec_to_dict(t: TransitionSpec) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": t.kind}
    if t.duration_ms is not None:
        out["duration_ms"] = t.duration_ms
    if t.easing is not None:
        out["easing"] = t.easing
    if t.stiffness is not None:
        out["stiffness"] = t.stiffness
    if t.damping is not None:
        out["damping"] = t.damping
    return out


def _cause_to_dict(c: Cause) -> dict[str, Any]:
    out: dict[str, Any] = {"source": c.source}
    if c.input_id is not None:
        out["input_id"] = c.input_id
    return out


def _scene_transition_to_dict(t: SceneTransition) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": t.kind}
    if t.duration_ms is not None:
        out["duration_ms"] = t.duration_ms
    return out
