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


def test_observe_first_must_be_one() -> None:
    t = SequenceTracker()
    with pytest.raises(InvalidSeqStartError):
        t.observe_server(2)


def test_observe_one_resets_after_scene_changed() -> None:
    t = SequenceTracker()
    t.observe_server(1)
    t.observe_server(2)
    t.observe_server(3)
    # scene_changed → next snapshot at seq=1 again.
    assert t.observe_server(1) is False
    assert t.observe_server(2) is False
