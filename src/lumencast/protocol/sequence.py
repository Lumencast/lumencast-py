"""Per-subscription sequence tracker with gap detection."""

from __future__ import annotations

import threading


class GapError(Exception):
    """Sequence gap detected on the server-to-client stream.

    The receiver MUST close the WebSocket and reconnect — a fresh
    snapshot will reset state.
    """


class InvalidSeqStartError(Exception):
    """First frame of a subscription does not carry ``seq == 1``."""


class SequenceTracker:
    """Thread-safe per-subscription monotonic counter.

    On the server side, :meth:`next_server` returns the next outgoing
    seq for a frame the kit is about to emit. Call :meth:`reset` before
    the snapshot that follows a ``scene_changed``.

    On the receiver side, :meth:`observe_server` advances the tracker
    according to LSDP/1 § 5 :

    - ``seq == 1`` is always accepted (fresh subscription / scene_changed).
    - ``seq == cur + 1`` advances normally.
    - ``seq <= cur`` is a silent replay — caller drops the frame.
    - ``seq > cur + 1`` is a gap — caller must close + reconnect.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cur: int = 0

    def next_server(self) -> int:
        """Allocate the next outgoing seq for a server-emitted frame."""
        with self._lock:
            self._cur += 1
            return self._cur

    def reset(self) -> None:
        """Rewind the counter so the next ``next_server`` returns ``1``."""
        with self._lock:
            self._cur = 0

    def current(self) -> int:
        """Return the last seq emitted (``0`` if none yet)."""
        with self._lock:
            return self._cur

    def observe_server(self, seq: int) -> bool:
        """Validate an incoming server frame's seq.

        Returns True if the caller should drop the frame as a replay.
        Returns False if the frame is the next expected value (caller
        proceeds normally). Raises :class:`GapError` on a gap or
        :class:`InvalidSeqStartError` if the first observed seq is not 1.
        """
        with self._lock:
            if seq == 1:
                self._cur = 1
                return False
            if self._cur == 0:
                raise InvalidSeqStartError(
                    f"protocol: subscription must start at seq=1, got seq={seq}"
                )
            if seq == self._cur + 1:
                self._cur = seq
                return False
            if seq <= self._cur:
                return True
            raise GapError(f"protocol: sequence gap, expected {self._cur + 1}, got {seq}")
