"""Typed LSDP/1 frames as frozen dataclasses.

Every frame is constructed with its semantic fields ; the codec stamps
``v`` and ``type`` automatically on encode. Frames are kept lightweight :
``state`` and ``patches`` carry plain Python values (``dict``, ``list``,
JSON scalars), not pydantic models, because LSDP/1 is forward-compatible
on unknown values and we want to round-trip them losslessly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class TransitionSpec:
    """Per-leaf animation directive on a delta patch (LSDP/1.1 §3.2.2).

    Servers MAY emit ; runtimes interpret when applying the new value.
    1.0 receivers ignore. ``kind`` is one of ``"tween"``, ``"spring"``,
    or ``"snap"`` ; the remaining fields are per-kind and the encoder
    omits whichever ones are unset.
    """

    kind: Literal["tween", "spring", "snap"]
    duration_ms: int | None = None
    easing: Literal["linear", "ease-in", "ease-out", "ease-in-out"] | None = None
    stiffness: float | None = None
    damping: float | None = None


@dataclass(slots=True)
class Cause:
    """Optional provenance metadata on a delta (LSDP/1.1 §3.2.3).

    Receivers MUST NOT use it for semantic decisions — debug/audit
    only. ``input_id`` echoes the originating ``Input.client_msg_id``
    when applicable.
    """

    source: str
    input_id: str | None = None


@dataclass(slots=True)
class SceneTransition:
    """Show-level scene-swap transition on a ``SceneChanged`` frame
    (LSDP/1.1 §3.3.1).

    ``kind`` is a free-form string ; ``"crossfade"`` is the standard
    1.1 value, vendor-prefixed ``x-vendor.*`` kinds are also accepted
    on the wire (per §17.1 / §17.2 — runtime support is out of scope).
    """

    kind: str
    duration_ms: int | None = None


@dataclass(slots=True)
class Patch:
    """Single leaf patch — a path and its new JSON value.

    May carry a 1.1 ``TransitionSpec`` directing the runtime how to
    interpolate to the new value. 1.0 receivers ignore the field.
    """

    path: str
    value: Any
    transition: TransitionSpec | None = None


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
    May carry a 1.1 ``cause`` for provenance.
    """

    patches: list[Patch] = field(default_factory=list)
    seq: int = 0
    ts: str = ""
    cause: Cause | None = None


@dataclass(slots=True)
class SceneChanged:
    """Active scene was swapped server-side.

    The next server frame after a ``SceneChanged`` MUST be a Snapshot
    with ``seq = 1``. May carry the 1.1 ``from_scene_id`` and show-level
    ``transition`` (§3.3.1).
    """

    scene_id: str
    scene_version: str
    seq: int = 0
    ts: str = ""
    from_scene_id: str | None = None
    transition: SceneTransition | None = None


@dataclass(slots=True)
class Error:
    """Server-emitted error frame.

    ``recoverable=False`` signals the server will close the WebSocket
    within 1 second. ``retry_after_ms`` is optional, set on
    ``RATE_LIMIT`` to suggest a throttle hint.

    ``path`` is REQUIRED on path-scoped codes (``WRITE_FORBIDDEN``,
    ``UNKNOWN_PATH``, ``INVALID_VALUE``) per LSDP/1.0.1 §3.4.1.
    """

    code: str
    message: str
    recoverable: bool
    seq: int = 0
    ts: str = ""
    retry_after_ms: int = 0
    path: str | None = None


@dataclass(slots=True)
class Pong:
    """Heartbeat reply. Carries no seq — heartbeats are out-of-band per § 5.

    May echo a 1.1 ``nonce`` correlation tag from the matching Ping.
    """

    nonce: str | None = None


@dataclass(slots=True)
class Ping:
    """Heartbeat probe. Receiver MUST reply with Pong within 5 seconds.

    May carry a 1.1 ``nonce`` for latency-probe correlation.
    """

    nonce: str | None = None


@dataclass(slots=True)
class Subscribe:
    """First frame a client sends after the WebSocket open.

    ``scene`` and ``session`` are conditional : required for test mode,
    forbidden for live mode. The server enforces the conditional ; the
    codec is permissive.

    ``since_sequence`` (1.1 §4.1, §18) requests an incremental resume from
    a known last-seen seq. ``None`` means no resume requested.
    """

    token: str
    scene: str = ""
    session: str = ""
    since_sequence: int | None = None


@dataclass(slots=True)
class Input:
    """Operator input frame — atomic patch list.

    Allowed for clients with the ``operator``, ``service``, or ``test``
    role. The server rejects the entire frame if any patch is invalid.

    ``client_msg_id`` (1.1 §4.2) is a free-form correlation tag the
    server MUST echo verbatim into ``Cause.input_id`` of the resulting
    delta.
    """

    patches: list[Patch] = field(default_factory=list)
    client_msg_id: str | None = None


@dataclass(slots=True)
class Unsubscribe:
    """Clean-teardown signal (LSDP/1.1 §4.4).

    The server MUST close the WebSocket within 1 second of receipt.
    No data flows after this frame.
    """
