"""Byte-level conformance fixture round-trip.

Walks the fixture index from ``lumencast-protocol/conformance/manifest.json``
and verifies each fixture round-trips through our codec without losing
field-level fidelity.

Set ``LUMENCAST_PROTOCOL_REPO`` to the lumencast-protocol checkout so the
fixture loader knows where to look. CI does this automatically.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from lumencast.protocol.codec import decode_client, decode_server, encode
from lumencast.protocol.envelope import decode_json
from lumencast.protocol.frames import (
    Delta,
    Error,
    Input,
    Ping,
    Pong,
    SceneChanged,
    Snapshot,
    Subscribe,
)


def _resolve_fixtures_dir() -> Path | None:
    env = os.environ.get("LUMENCAST_PROTOCOL_REPO")
    if env:
        candidate = Path(env) / "conformance" / "v1" / "fixtures"
        if candidate.is_dir():
            return candidate
    sibling = Path.cwd().parent / "lumencast-protocol" / "conformance" / "v1" / "fixtures"
    if sibling.is_dir():
        return sibling
    return None


_FIXTURES = _resolve_fixtures_dir()


@pytest.mark.conformance
@pytest.mark.skipif(
    _FIXTURES is None,
    reason="lumencast-protocol checkout not found (set LUMENCAST_PROTOCOL_REPO)",
)
def test_fixture_index_loadable() -> None:
    assert _FIXTURES is not None
    files = sorted(_FIXTURES.rglob("*.json"))
    assert files, "expected at least one fixture under fixtures/"


def _all_fixtures() -> list[Path]:
    if _FIXTURES is None:
        return []
    return sorted(_FIXTURES.rglob("*.json"))


@pytest.mark.conformance
@pytest.mark.skipif(
    _FIXTURES is None,
    reason="lumencast-protocol checkout not found (set LUMENCAST_PROTOCOL_REPO)",
)
@pytest.mark.parametrize(
    "fixture",
    _all_fixtures(),
    ids=lambda p: p.relative_to(_FIXTURES).as_posix() if _FIXTURES else str(p),
)
def test_fixture_round_trip(fixture: Path) -> None:
    """Each fixture decodes, re-encodes, and matches the on-wire shape.

    "Match" is an envelope-level deep compare : every key/value the
    fixture declares MUST appear on the re-encoded frame. Optional fields
    omitted from the fixture stay omitted on re-encode (per spec § 2
    forward-compat allowance).
    """
    raw = fixture.read_text(encoding="utf-8").strip()
    obj = decode_json(raw)
    frame_type = obj.get("type")

    server_types = {"snapshot", "delta", "scene_changed", "error", "pong"}
    client_types = {"subscribe", "input", "ping"}

    parsed: object
    if frame_type in server_types:
        parsed = decode_server(raw)
        assert isinstance(
            parsed,
            (Snapshot, Delta, SceneChanged, Error, Pong),
        ), f"unexpected parsed type: {type(parsed).__name__}"
    elif frame_type in client_types:
        parsed = decode_client(raw)
        assert isinstance(parsed, (Subscribe, Input, Ping))
    else:
        pytest.skip(f"unknown frame type {frame_type!r} in fixture")

    re_encoded = encode(parsed)
    re_obj = json.loads(re_encoded)

    # Every field declared in the fixture MUST round-trip identically.
    _assert_subset(obj, re_obj, fixture.name)


def _assert_subset(expected: dict[str, Any], actual: dict[str, Any], name: str) -> None:
    for k, v in expected.items():
        assert k in actual, f"{name}: re-encoded missing field {k!r}"
        if isinstance(v, dict) and isinstance(actual[k], dict):
            _assert_subset(v, actual[k], f"{name}.{k}")
            continue
        if isinstance(v, list):
            assert isinstance(actual[k], list), f"{name}.{k}: type drift"
            assert len(v) == len(actual[k]), f"{name}.{k}: length drift"
            for i, (ev, av) in enumerate(zip(v, actual[k], strict=True)):
                if isinstance(ev, dict) and isinstance(av, dict):
                    _assert_subset(ev, av, f"{name}.{k}[{i}]")
                else:
                    assert ev == av, f"{name}.{k}[{i}]: {ev!r} != {av!r}"
            continue
        assert v == actual[k], f"{name}.{k}: {v!r} != {actual[k]!r}"
