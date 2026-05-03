"""Lumencast server kit — FastAPI + WebSocket implementation of LSDP/1.

Public surface : :class:`Server` (the kit), :class:`Scene`, the
authentication primitives, the input spec.

Heavy dependencies (``fastapi``, ``uvicorn``, ``websockets``) live in the
``[server]`` extra. Importing this package without them raises a clear
``ImportError`` pointing at the install command.
"""

from __future__ import annotations

from lumencast.server.auth import (
    Anonymous,
    Authenticator,
    AuthError,
    Identity,
    StaticTokens,
)
from lumencast.server.input import InputSpec, check_constraint
from lumencast.server.role import role_can_write
from lumencast.server.scene import EmptyPatchesError, Scene
from lumencast.server.server import Server
from lumencast.server.store import Store

__all__ = [
    "Anonymous",
    "AuthError",
    "Authenticator",
    "EmptyPatchesError",
    "Identity",
    "InputSpec",
    "Scene",
    "Server",
    "StaticTokens",
    "Store",
    "check_constraint",
    "role_can_write",
]
