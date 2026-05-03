"""LSDP/1 encode / decode for typed frames.

The codec is the only piece of the SDK allowed to assemble or parse a
wire frame. Every other layer round-trips through these functions, which
keeps the byte-level conformance fixtures load-bearing.
"""

from __future__ import annotations

from typing import Any

from lumencast.protocol.envelope import VERSION, decode_json, encode_json
from lumencast.protocol.frames import (
    Delta,
    Error,
    Input,
    Patch,
    Ping,
    Pong,
    SceneChanged,
    Snapshot,
    Subscribe,
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


def decode_client(raw: str | bytes) -> Subscribe | Input | Ping | Pong:
    """Parse a client-emitted frame.

    Server use. Returns one of (:class:`Subscribe`, :class:`Input`,
    :class:`Ping`, :class:`Pong`). Pong because clients may answer
    server-initiated pings.
    """
    env = _parse_envelope(raw)
    t = env["type"]
    if t == FRAME_SUBSCRIBE:
        return Subscribe(
            token=env.get("token", ""),
            scene=env.get("scene", "") or "",
            session=env.get("session", "") or "",
        )
    if t == FRAME_INPUT:
        return Input(patches=_parse_patches(env.get("patches")))
    if t == FRAME_PING:
        return Ping()
    if t == FRAME_PONG:
        return Pong()
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
        )
    if t == FRAME_SCENE_CHANGED:
        return SceneChanged(
            seq=int(env.get("seq", 0)),
            ts=env.get("ts", "") or "",
            scene_id=env.get("scene_id", ""),
            scene_version=env.get("scene_version", ""),
        )
    if t == FRAME_ERROR:
        return Error(
            seq=int(env.get("seq", 0)),
            ts=env.get("ts", "") or "",
            code=env.get("code", ""),
            message=env.get("message", ""),
            recoverable=bool(env.get("recoverable", False)),
            retry_after_ms=int(env.get("retry_after_ms", 0) or 0),
        )
    if t == FRAME_PONG:
        return Pong()
    if t == FRAME_PING:
        return Ping()
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
        out.append(Patch(path=str(item["path"]), value=item.get("value")))
    return out


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
        return out
    if isinstance(msg, Pong):
        return {"v": VERSION, "type": FRAME_PONG}
    if isinstance(msg, Ping):
        return {"v": VERSION, "type": FRAME_PING}
    if isinstance(msg, Subscribe):
        out = {"v": VERSION, "type": FRAME_SUBSCRIBE, "token": msg.token}
        if msg.scene:
            out["scene"] = msg.scene
        if msg.session:
            out["session"] = msg.session
        return out
    if isinstance(msg, Input):
        return {
            "v": VERSION,
            "type": FRAME_INPUT,
            "patches": [_patch_to_dict(p) for p in msg.patches],
        }
    raise TypeError(f"protocol: cannot encode {type(msg).__name__}")


def _patch_to_dict(p: Patch) -> dict[str, Any]:
    return {"path": p.path, "value": p.value}
