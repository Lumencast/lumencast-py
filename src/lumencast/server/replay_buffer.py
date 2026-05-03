"""Per-scene replay buffer (LSDP/1.1 §18.1).

Bounded ring of recent ``(seq, patches, cause)`` emissions so a 1.1
client reconnecting with ``since_sequence`` can resume without a fresh
snapshot.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from lumencast.protocol.frames import Cause, Patch

DEFAULT_REPLAY_BUFFER_SIZE: int = 256
"""Default capacity (LSDP/1.1 §18.1 SHOULD ≥ 256)."""


@dataclass(slots=True)
class ReplayRecord:
    """One entry in the replay buffer."""

    seq: int
    patches: list[Patch]
    cause: Cause | None = None


@dataclass(slots=True)
class ReplaySlice:
    """Outcome of a ``since`` query.

    ``covered=False`` means the requested resume point is older than
    the buffer's earliest entry — caller MUST fall back to a fresh
    snapshot per §18.1.
    """

    records: list[ReplayRecord]
    covered: bool


class ReplayBuffer:
    """Bounded ring of replay records."""

    def __init__(self, capacity: int = DEFAULT_REPLAY_BUFFER_SIZE) -> None:
        cap = capacity if capacity > 0 else DEFAULT_REPLAY_BUFFER_SIZE
        self._records: deque[ReplayRecord] = deque(maxlen=cap)

    def push(self, record: ReplayRecord) -> None:
        """Record one emission. Caller is responsible for monotonic seq."""
        self._records.append(record)

    def since(self, since_seq: int) -> ReplaySlice:
        """Return every record with ``seq > since_seq``, in monotonic order."""
        if not self._records:
            # Empty buffer — caller decides whether sinceSeq matches the
            # current scene seq (caught up) or warrants a snapshot.
            return ReplaySlice(records=[], covered=True)
        earliest = self._records[0].seq
        if since_seq + 1 < earliest:
            return ReplaySlice(records=[], covered=False)
        out = [r for r in self._records if r.seq > since_seq]
        return ReplaySlice(records=out, covered=True)

    def reset(self) -> None:
        """Clear the buffer. Used on ``scene_changed``."""
        self._records.clear()

    def __len__(self) -> int:
        return len(self._records)
