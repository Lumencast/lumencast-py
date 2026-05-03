"""Frame matcher tests."""

from __future__ import annotations

import pytest

from lumencast.conformance.match import match_frame, match_value


def test_match_strict_equality() -> None:
    match_frame({"a": 1, "b": "x"}, {"a": 1, "b": "x", "extra": True})


def test_match_missing_field() -> None:
    with pytest.raises(AssertionError, match="missing field"):
        match_frame({"a": 1}, {"b": 2})


def test_match_any_sentinel() -> None:
    match_value("$ANY", 12345, "ts")
    match_value("$ANY", "literal", "ts")


def test_match_any_hash() -> None:
    match_value("$ANY_HASH", "sha256:" + "a" * 64, "scene_version")


def test_match_any_hash_rejects_non_sha256() -> None:
    with pytest.raises(AssertionError, match="not a sha256 hash"):
        match_value("$ANY_HASH", "not-a-hash", "scene_version")


def test_match_numeric_tower() -> None:
    # YAML int vs JSON float — both should compare equal.
    match_value(1, 1.0, "n")
    match_value(1.0, 1, "n")


def test_match_bool_strict() -> None:
    # bool MUST NOT be equal to its int counterpart.
    with pytest.raises(AssertionError):
        match_value(True, 1, "flag")


def test_match_list_lengths() -> None:
    with pytest.raises(AssertionError, match="length"):
        match_value([1, 2], [1, 2, 3], "patches")


def test_match_recursive_dict() -> None:
    expected = {"state": {"a": 1, "b": "$ANY"}}
    actual = {"state": {"a": 1, "b": [1, 2, 3]}, "extra": True}
    match_frame(expected, actual)
