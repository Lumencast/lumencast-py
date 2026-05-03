"""LSDP/1.1 — additive frame surface round-trip tests.

Mirrors lumencast-go/protocol/protocol_test.go,
lumencast-js/packages/protocol/tests/v1_1.test.ts, and
lumencast-rs/crates/lumencast-protocol/tests/round_trip.rs.
"""

from __future__ import annotations

import pytest

from lumencast.protocol.codec import DecodeError, decode_client, decode_server, encode
from lumencast.protocol.envelope import SUBPROTOCOL, SUBPROTOCOL_V1_1, SUBPROTOCOLS
from lumencast.protocol.frames import (
    Cause,
    Delta,
    Input,
    Patch,
    Ping,
    Pong,
    SceneChanged,
    SceneTransition,
    Subscribe,
    TransitionSpec,
    Unsubscribe,
)


def test_subprotocol_constants() -> None:
    assert SUBPROTOCOL == "lsdp.v1"
    assert SUBPROTOCOL_V1_1 == "lsdp.v1.1"
    # Preference order : 1.1 first, 1.0 fallback.
    assert SUBPROTOCOLS == ("lsdp.v1.1", "lsdp.v1")


def test_subscribe_with_since_sequence_round_trips() -> None:
    frame = Subscribe(token="t", since_sequence=12345)
    raw = encode(frame)
    assert raw == '{"v":1,"type":"subscribe","token":"t","since_sequence":12345}'
    decoded = decode_client(raw)
    assert isinstance(decoded, Subscribe)
    assert decoded.since_sequence == 12345


def test_bare_subscribe_omits_since_sequence() -> None:
    raw = encode(Subscribe(token="t"))
    assert "since_sequence" not in raw


def test_input_with_client_msg_id_round_trips() -> None:
    frame = Input(
        patches=[Patch(path="__inputs.title", value="Hello")],
        client_msg_id="ui-9f3a",
    )
    raw = encode(frame)
    assert '"client_msg_id":"ui-9f3a"' in raw
    decoded = decode_client(raw)
    assert isinstance(decoded, Input)
    assert decoded.client_msg_id == "ui-9f3a"


def test_input_without_client_msg_id_omits_field() -> None:
    raw = encode(Input(patches=[Patch(path="x", value=1)]))
    assert "client_msg_id" not in raw


def test_ping_pong_nonce_round_trips() -> None:
    raw_ping = encode(Ping(nonce="probe-7a2c"))
    assert raw_ping == '{"v":1,"type":"ping","nonce":"probe-7a2c"}'
    decoded_ping = decode_client(raw_ping)
    assert isinstance(decoded_ping, Ping)
    assert decoded_ping.nonce == "probe-7a2c"

    raw_pong = encode(Pong(nonce="probe-7a2c"))
    assert raw_pong == '{"v":1,"type":"pong","nonce":"probe-7a2c"}'
    decoded_pong = decode_server(raw_pong)
    assert isinstance(decoded_pong, Pong)
    assert decoded_pong.nonce == "probe-7a2c"

    # Bare ping/pong omit nonce on the wire.
    assert encode(Ping()) == '{"v":1,"type":"ping"}'
    assert encode(Pong()) == '{"v":1,"type":"pong"}'


def test_unsubscribe_round_trips() -> None:
    raw = encode(Unsubscribe())
    assert raw == '{"v":1,"type":"unsubscribe"}'
    decoded = decode_client(raw)
    assert isinstance(decoded, Unsubscribe)


def test_delta_with_cause_and_transition_round_trips() -> None:
    transition = TransitionSpec(kind="tween", duration_ms=500, easing="ease-out")
    cause = Cause(source="operator:alice", input_id="ui-9f3a")
    frame = Delta(
        seq=7,
        patches=[Patch(path="score", value=42, transition=transition)],
        cause=cause,
    )
    raw = encode(frame)
    assert '"transition":{"kind":"tween"' in raw
    assert '"easing":"ease-out"' in raw
    assert '"cause":{"source":"operator:alice"' in raw

    decoded = decode_server(raw)
    assert isinstance(decoded, Delta)
    assert decoded.cause is not None
    assert decoded.cause.input_id == "ui-9f3a"
    assert decoded.patches[0].transition is not None
    assert decoded.patches[0].transition.kind == "tween"
    assert decoded.patches[0].transition.duration_ms == 500


def test_scene_changed_with_transition_round_trips() -> None:
    frame = SceneChanged(
        seq=100,
        scene_id="scene-b",
        scene_version="sha256:b0",
        from_scene_id="scene-a",
        transition=SceneTransition(kind="crossfade", duration_ms=600),
    )
    raw = encode(frame)
    assert '"from_scene_id":"scene-a"' in raw
    assert '"transition":{"kind":"crossfade","duration_ms":600}' in raw
    decoded = decode_server(raw)
    assert isinstance(decoded, SceneChanged)
    assert decoded.from_scene_id == "scene-a"
    assert decoded.transition is not None
    assert decoded.transition.kind == "crossfade"
    assert decoded.transition.duration_ms == 600


def test_invalid_transition_kind_rejected() -> None:
    raw = '{"v":1,"type":"delta","seq":1,"patches":[{"path":"x","value":1,"transition":{"kind":"warp"}}]}'
    with pytest.raises(DecodeError, match=r"transition\.kind"):
        decode_server(raw)


def test_cause_without_source_rejected() -> None:
    raw = '{"v":1,"type":"delta","seq":1,"patches":[{"path":"x","value":1}],"cause":{"input_id":"x"}}'
    with pytest.raises(DecodeError, match=r"cause\.source"):
        decode_server(raw)


def test_forward_compat_1_0_decodes_1_1_delta() -> None:
    raw = '{"v":1,"type":"delta","seq":1,"patches":[{"path":"x","value":1}],"cause":{"source":"adapter:http_poll"}}'
    decoded = decode_server(raw)
    assert isinstance(decoded, Delta)
    assert decoded.seq == 1
    assert decoded.cause is not None
    assert decoded.cause.source == "adapter:http_poll"


def test_backward_compat_1_0_subscribe_byte_identical() -> None:
    # 1.0-style caller producing the legacy wire shape unchanged.
    raw = encode(Subscribe(token="t"))
    assert raw == '{"v":1,"type":"subscribe","token":"t"}'


def test_backward_compat_1_0_delta_byte_identical() -> None:
    raw = encode(Delta(seq=1, patches=[Patch(path="x", value=1)]))
    assert raw == '{"v":1,"type":"delta","seq":1,"patches":[{"path":"x","value":1}]}'
