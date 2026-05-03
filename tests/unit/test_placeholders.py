"""Placeholder substitution tests."""

from __future__ import annotations

from lumencast.conformance.placeholders import substitute_placeholders


def test_token_substitution() -> None:
    out = substitute_placeholders("$TOKEN_OPERATOR", {"$TOKEN_OPERATOR": "tok-1"}, {})
    assert out == "tok-1"


def test_unknown_token_passes_through() -> None:
    out = substitute_placeholders("$TOKEN_GHOST", {}, {})
    assert out == "$TOKEN_GHOST"


def test_bundle_hash_substitution() -> None:
    out = substitute_placeholders("$BUNDLE.foo.hash", {}, {"foo": "sha256:abc"})
    assert out == "sha256:abc"


def test_recursive_dict_and_list() -> None:
    payload = {
        "v": 1,
        "type": "subscribe",
        "token": "$TOKEN_OPERATOR",
        "patches": [{"value": "$BUNDLE.b.hash"}],
    }
    out = substitute_placeholders(
        payload,
        {"$TOKEN_OPERATOR": "tok"},
        {"b": "sha256:1"},
    )
    assert out == {
        "v": 1,
        "type": "subscribe",
        "token": "tok",
        "patches": [{"value": "sha256:1"}],
    }


def test_non_placeholder_strings_unchanged() -> None:
    out = substitute_placeholders("plain", {"$TOKEN_X": "tok"}, {})
    assert out == "plain"
