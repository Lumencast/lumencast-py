"""Unit tests for the per-scene replay buffer (LSDP/1.1 §18.1)."""

from __future__ import annotations

from lumencast.protocol.frames import Patch
from lumencast.server.replay_buffer import ReplayBuffer, ReplayRecord


def _rec(seq: int) -> ReplayRecord:
    return ReplayRecord(seq=seq, patches=[Patch(path="x", value=seq)])


def test_push_then_since_returns_everything() -> None:
    b = ReplayBuffer(4)
    for i in range(1, 4):
        b.push(_rec(i))
    assert len(b) == 3
    s = b.since(0)
    assert s.covered is True
    assert [r.seq for r in s.records] == [1, 2, 3]


def test_ring_wraparound() -> None:
    b = ReplayBuffer(4)
    for i in range(1, 11):
        b.push(_rec(i))
    assert len(b) == 4
    s = b.since(6)
    assert s.covered is True
    assert [r.seq for r in s.records] == [7, 8, 9, 10]


def test_gap_not_covered() -> None:
    b = ReplayBuffer(4)
    for i in range(1, 11):
        b.push(_rec(i))
    # Earliest retained is 7 ; since=2 means "give me 3..10" but we
    # only have 7..10.
    assert b.since(2).covered is False


def test_caught_up() -> None:
    b = ReplayBuffer(4)
    for i in range(1, 4):
        b.push(_rec(i))
    s = b.since(3)
    assert s.covered is True
    assert s.records == []


def test_reset_clears() -> None:
    b = ReplayBuffer(4)
    b.push(_rec(1))
    b.reset()
    assert len(b) == 0


def test_empty_buffer_always_covered() -> None:
    b = ReplayBuffer(4)
    s = b.since(99)
    assert s.covered is True
    assert s.records == []
