"""Codec round-trip and dispatch tests."""

from __future__ import annotations

import json

import pytest

from lumencast.protocol.codec import (
    DecodeError,
    UnknownTypeError,
    VersionMismatchError,
    decode_client,
    decode_server,
    encode,
)
from lumencast.protocol.frames import (
    Delta,
    Error,
    Input,
    Patch,
    Ping,
    Pong,
    SceneChanged,
    Snapshot,
    Subscribe,
)


def test_snapshot_round_trip() -> None:
    snap = Snapshot(
        scene_id="main",
        scene_version="sha256:abc",
        state={"a": 1, "b": "hi"},
        seq=1,
    )
    raw = encode(snap)
    parsed = decode_server(raw)
    assert isinstance(parsed, Snapshot)
    assert parsed.scene_id == "main"
    assert parsed.state == {"a": 1, "b": "hi"}
    assert parsed.seq == 1


def test_delta_round_trip() -> None:
    d = Delta(patches=[Patch(path="a", value=1), Patch(path="b", value="x")], seq=2)
    raw = encode(d)
    parsed = decode_server(raw)
    assert isinstance(parsed, Delta)
    assert [(p.path, p.value) for p in parsed.patches] == [("a", 1), ("b", "x")]


def test_subscribe_round_trip() -> None:
    s = Subscribe(token="t-1", scene="main", session="s-1")
    raw = encode(s)
    parsed = decode_client(raw)
    assert isinstance(parsed, Subscribe)
    assert parsed.token == "t-1"
    assert parsed.scene == "main"
    assert parsed.session == "s-1"


def test_subscribe_omits_empty_optionals_on_wire() -> None:
    raw = encode(Subscribe(token="t"))
    obj = json.loads(raw)
    assert "scene" not in obj
    assert "session" not in obj


def test_input_round_trip() -> None:
    i = Input(patches=[Patch(path="__inputs.title", value="x")])
    raw = encode(i)
    parsed = decode_client(raw)
    assert isinstance(parsed, Input)
    assert parsed.patches[0].path == "__inputs.title"


def test_error_recoverable_flag() -> None:
    e = Error(code="WRITE_FORBIDDEN", message="nope", recoverable=True, seq=3)
    raw = encode(e)
    parsed = decode_server(raw)
    assert isinstance(parsed, Error)
    assert parsed.recoverable is True


def test_pong_ping_minimal() -> None:
    assert decode_server(encode(Pong())) == Pong()
    assert decode_client(encode(Ping())) == Ping()


def test_scene_changed_round_trip() -> None:
    sc = SceneChanged(scene_id="next", scene_version="sha256:def", seq=42)
    raw = encode(sc)
    parsed = decode_server(raw)
    assert isinstance(parsed, SceneChanged)
    assert parsed.seq == 42


def test_decode_rejects_wrong_version() -> None:
    raw = '{"v":2,"type":"snapshot","seq":1,"scene_id":"x","scene_version":"y","state":{}}'
    with pytest.raises(VersionMismatchError):
        decode_server(raw)


def test_decode_rejects_unknown_type() -> None:
    raw = '{"v":1,"type":"future_frame"}'
    with pytest.raises(UnknownTypeError):
        decode_server(raw)


def test_decode_rejects_invalid_json() -> None:
    with pytest.raises(DecodeError):
        decode_server("not json")


def test_encode_rejects_unknown_type() -> None:
    with pytest.raises(TypeError):
        encode(object())
