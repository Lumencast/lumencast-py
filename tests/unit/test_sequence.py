"""SequenceTracker tests covering server-side allocation and observe gaps."""

from __future__ import annotations

import pytest

from lumencast.protocol.sequence import (
    GapError,
    InvalidSeqStartError,
    SequenceTracker,
)


def test_next_server_starts_at_one() -> None:
    t = SequenceTracker()
    assert t.next_server() == 1
    assert t.next_server() == 2
    assert t.current() == 2


def test_reset_rewinds() -> None:
    t = SequenceTracker()
    t.next_server()
    t.next_server()
    t.reset()
    assert t.next_server() == 1


def test_observe_normal_progression() -> None:
    t = SequenceTracker()
    assert t.observe_server(1) is False
    assert t.observe_server(2) is False
    assert t.observe_server(3) is False


def test_observe_replay_returns_true() -> None:
    t = SequenceTracker()
    t.observe_server(1)
    t.observe_server(2)
    t.observe_server(3)
    # seq <= cur on the same subscription is a silent replay.
    assert t.observe_server(3) is True
    assert t.observe_server(2) is True
    # seq == 1 is always treated as a fresh start (post-scene_changed or
    # fresh subscription), NOT as a replay — the receiver cannot tell the
    # two cases apart without external context.


def test_observe_gap_raises() -> None:
    t = SequenceTracker()
    t.observe_server(1)
    with pytest.raises(GapError):
        t.observe_server(3)


def test_observe_first_accepts_any_positive() -> None:
    # LSDP/1.1 §18.1.1 — fresh tracker accepts any seq >= 1 as the
    # baseline (per-scene seq, late-joining subscribers may see snapshot
    # at seq > 1). Only seq=0 is rejected.
    t = SequenceTracker()
    assert t.observe_server(42) is False
    assert t.observe_server(43) is False
    assert t.current() == 43


def test_observe_seq_zero_rejected() -> None:
    t = SequenceTracker()
    with pytest.raises(InvalidSeqStartError):
        t.observe_server(0)


def test_observe_snapshot_rebases() -> None:
    # After scene_changed or back-pressure recovery, observe_snapshot
    # rebases the tracker to the snapshot's seq regardless of previous
    # state.
    t = SequenceTracker()
    t.observe_server(1)
    t.observe_server(2)
    t.observe_server(3)
    t.observe_snapshot(1)  # new scene, fresh seq=1
    assert t.observe_server(2) is False
    assert t.current() == 2
