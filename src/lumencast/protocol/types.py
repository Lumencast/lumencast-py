"""Shared protocol-level enums and frame-type discriminators."""

from __future__ import annotations

from enum import Enum

# Frame type discriminators. Constants instead of strings so a typo in a
# handler is a name error rather than a silent runtime mismatch.
FRAME_SNAPSHOT: str = "snapshot"
FRAME_DELTA: str = "delta"
FRAME_SCENE_CHANGED: str = "scene_changed"
FRAME_ERROR: str = "error"
FRAME_PONG: str = "pong"
FRAME_SUBSCRIBE: str = "subscribe"
FRAME_INPUT: str = "input"
FRAME_PING: str = "ping"


class Role(str, Enum):
    """Connection-level authority assigned by token validation.

    Values match LSDP/1 § 9 verbatim. The string base class lets the role
    serialise to its own name in JSON (useful for ``Identity`` records
    leaving the process boundary).
    """

    VIEWER = "viewer"
    OPERATOR = "operator"
    SERVICE = "service"
    TEST = "test"

    def can_write_inputs(self) -> bool:
        """Return True if the role may write ``__inputs.*`` paths."""
        return self in {Role.OPERATOR, Role.SERVICE}

    def can_write_test(self) -> bool:
        """Return True if the role may write ``__test.*`` paths."""
        return self == Role.TEST
