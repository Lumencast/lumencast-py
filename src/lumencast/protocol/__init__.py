"""LSDP/1 wire codec — pure protocol, no IO.

Re-exports the everyday surface so callers can ``from lumencast.protocol
import Snapshot, decode``.
"""

from __future__ import annotations

from lumencast.protocol.codec import (
    DecodeError,
    UnknownTypeError,
    VersionMismatchError,
    decode_client,
    decode_server,
    encode,
)
from lumencast.protocol.envelope import SUBPROTOCOL, VERSION
from lumencast.protocol.errors import ErrorCode, LumencastError
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
from lumencast.protocol.leaf_path import (
    LeafPath,
    is_reserved,
    namespace,
    substitute,
    validate_path,
)
from lumencast.protocol.sequence import (
    GapError,
    InvalidSeqStartError,
    SequenceTracker,
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
    Role,
)

__all__ = [
    "FRAME_DELTA",
    "FRAME_ERROR",
    "FRAME_INPUT",
    "FRAME_PING",
    "FRAME_PONG",
    "FRAME_SCENE_CHANGED",
    "FRAME_SNAPSHOT",
    "FRAME_SUBSCRIBE",
    "SUBPROTOCOL",
    "VERSION",
    "DecodeError",
    "Delta",
    "Error",
    "ErrorCode",
    "GapError",
    "Input",
    "InvalidSeqStartError",
    "LeafPath",
    "LumencastError",
    "Patch",
    "Ping",
    "Pong",
    "Role",
    "SceneChanged",
    "SequenceTracker",
    "Snapshot",
    "Subscribe",
    "UnknownTypeError",
    "VersionMismatchError",
    "decode_client",
    "decode_server",
    "encode",
    "is_reserved",
    "namespace",
    "substitute",
    "validate_path",
]
