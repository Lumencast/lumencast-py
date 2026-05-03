"""Closed taxonomy of LSDP/1 error codes.

The set is frozen for LSDP/1.x ; new codes require a minor version bump
per spec § 13. See ``ERROR-CODES.md`` in ``lumencast-protocol`` for the
authoritative semantics of each code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ErrorCode(str, Enum):
    """Stable string identifier for the LSDP/1 error frame ``code`` field.

    Each code has a fixed recoverability — see :meth:`recoverable`.
    """

    AUTH_DENIED = "AUTH_DENIED"
    WRITE_FORBIDDEN = "WRITE_FORBIDDEN"
    SCENE_NOT_FOUND = "SCENE_NOT_FOUND"
    BUNDLE_FETCH_FAILED = "BUNDLE_FETCH_FAILED"
    BUNDLE_INCOMPATIBLE = "BUNDLE_INCOMPATIBLE"
    VERSION_GAP = "VERSION_GAP"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    UNKNOWN_PATH = "UNKNOWN_PATH"
    INVALID_VALUE = "INVALID_VALUE"
    RATE_LIMIT = "RATE_LIMIT"
    TEST_SESSION_EXPIRED = "TEST_SESSION_EXPIRED"
    INTERNAL = "INTERNAL"

    def recoverable(self, internal_default: bool = False) -> bool:
        """Return the canonical recoverability for the code.

        ``INTERNAL`` returns ``internal_default`` because its semantics
        vary case-by-case (the server frame carries the actual flag).
        """
        if self in {
            ErrorCode.WRITE_FORBIDDEN,
            ErrorCode.BUNDLE_FETCH_FAILED,
            ErrorCode.VERSION_GAP,
            ErrorCode.UNKNOWN_PATH,
            ErrorCode.INVALID_VALUE,
            ErrorCode.RATE_LIMIT,
        }:
            return True
        if self in {
            ErrorCode.AUTH_DENIED,
            ErrorCode.SCENE_NOT_FOUND,
            ErrorCode.BUNDLE_INCOMPATIBLE,
            ErrorCode.VERSION_MISMATCH,
            ErrorCode.TEST_SESSION_EXPIRED,
        }:
            return False
        return internal_default


@dataclass(frozen=True, slots=True)
class LumencastError(Exception):
    """Runtime-friendly counterpart to a wire ``Error`` frame.

    Frozen dataclass so it can serve as a comparable error value across
    callbacks ; subclasses :class:`Exception` so it can be raised when
    a runtime treats an unrecoverable error as a fatal exception.
    """

    code: ErrorCode
    message: str
    recoverable: bool

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
