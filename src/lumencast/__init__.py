"""Lumencast Python SDK.

Public re-exports cover the everyday surface : protocol codec, server kit,
and error taxonomy. Conformance / interop / CLI live in their submodules.
"""

from __future__ import annotations

from lumencast._version import __version__
from lumencast.protocol.errors import ErrorCode, LumencastError
from lumencast.protocol.frames import (
    Delta,
    Input,
    Patch,
    Ping,
    Pong,
    SceneChanged,
    Snapshot,
    Subscribe,
)
from lumencast.protocol.frames import (
    Error as ErrorFrame,
)
from lumencast.protocol.types import Role

__all__ = [
    "Delta",
    "ErrorCode",
    "ErrorFrame",
    "Input",
    "LumencastError",
    "Patch",
    "Ping",
    "Pong",
    "Role",
    "SceneChanged",
    "Snapshot",
    "Subscribe",
    "__version__",
]
