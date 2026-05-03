"""Typed LSDP/1 frames as frozen dataclasses.

Every frame is constructed with its semantic fields ; the codec stamps
``v`` and ``type`` automatically on encode. Frames are kept lightweight :
``state`` and ``patches`` carry plain Python values (``dict``, ``list``,
JSON scalars), not pydantic models, because LSDP/1 is forward-compatible
on unknown values and we want to round-trip them losslessly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Patch:
    """Single leaf patch — a path and its new JSON value."""

    path: str
    value: Any


@dataclass(slots=True)
class Snapshot:
    """Full state of a subscription at a point in time.

    Server emits exactly one Snapshot per subscription (immediately after
    ``Subscribe``). Reconnection or ``SceneChanged`` triggers a new
    Snapshot with seq reset to 1.
    """

    scene_id: str
    scene_version: str
    state: dict[str, Any] = field(default_factory=dict)
    seq: int = 0
    ts: str = ""


@dataclass(slots=True)
class Delta:
    """Incremental patches applied to the existing state.

    Patches are atomic — the runtime MUST apply them all or none.
    """

    patches: list[Patch] = field(default_factory=list)
    seq: int = 0
    ts: str = ""


@dataclass(slots=True)
class SceneChanged:
    """Active scene was swapped server-side.

    The next server frame after a ``SceneChanged`` MUST be a Snapshot
    with ``seq = 1``.
    """

    scene_id: str
    scene_version: str
    seq: int = 0
    ts: str = ""


@dataclass(slots=True)
class Error:
    """Server-emitted error frame.

    ``recoverable=False`` signals the server will close the WebSocket
    within 1 second. ``retry_after_ms`` is optional, set on
    ``RATE_LIMIT`` to suggest a throttle hint.
    """

    code: str
    message: str
    recoverable: bool
    seq: int = 0
    ts: str = ""
    retry_after_ms: int = 0


@dataclass(slots=True)
class Pong:
    """Heartbeat reply. Carries no seq — heartbeats are out-of-band per § 5."""


@dataclass(slots=True)
class Ping:
    """Heartbeat probe. Receiver MUST reply with Pong within 5 seconds."""


@dataclass(slots=True)
class Subscribe:
    """First frame a client sends after the WebSocket open.

    ``scene`` and ``session`` are conditional : required for test mode,
    forbidden for live mode. The server enforces the conditional ; the
    codec is permissive.
    """

    token: str
    scene: str = ""
    session: str = ""


@dataclass(slots=True)
class Input:
    """Operator input frame — atomic patch list.

    Allowed for clients with the ``operator``, ``service``, or ``test``
    role. The server rejects the entire frame if any patch is invalid.
    """

    patches: list[Patch] = field(default_factory=list)
