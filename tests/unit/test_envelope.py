"""Round-trip tests for envelope.encode_json / decode_json."""

from __future__ import annotations

import pytest

from lumencast.protocol.envelope import SUBPROTOCOL, VERSION, decode_json, encode_json


def test_constants() -> None:
    assert VERSION == 1
    assert SUBPROTOCOL == "lsdp.v1"


def test_encode_compact_separators() -> None:
    raw = encode_json({"a": 1, "b": [2, 3]})
    assert raw == '{"a":1,"b":[2,3]}'


def test_encode_preserves_unicode() -> None:
    # Leaf paths and values should pass through verbatim — no \u escapes.
    raw = encode_json({"title": "café"})
    assert raw == '{"title":"café"}'


def test_decode_object_round_trip() -> None:
    obj = decode_json('{"v":1,"type":"snapshot","scene_id":"x"}')
    assert obj == {"v": 1, "type": "snapshot", "scene_id": "x"}


def test_decode_rejects_non_object() -> None:
    with pytest.raises(ValueError, match="JSON object"):
        decode_json("[1, 2, 3]")
