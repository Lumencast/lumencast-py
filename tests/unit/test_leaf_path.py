"""Leaf-path validation and substitution tests."""

from __future__ import annotations

import pytest

from lumencast.protocol.leaf_path import (
    has_prefix,
    is_reserved,
    namespace,
    substitute,
    validate_path,
)


@pytest.mark.parametrize("path", ["a", "show.title", "players.0.name", "__inputs.locale"])
def test_validate_accepts_well_formed(path: str) -> None:
    validate_path(path)


@pytest.mark.parametrize("path", ["", "a..b", "a.b.", ".a", "a-b", "a b", "a.{x}.c"])
def test_validate_rejects_malformed(path: str) -> None:
    with pytest.raises(ValueError):
        validate_path(path)


def test_validate_template_accepts_braces() -> None:
    validate_path("{player}.name", allow_template=True)


def test_validate_template_rejects_empty_scope() -> None:
    with pytest.raises(ValueError):
        validate_path("{}.x", allow_template=True)


def test_substitute_resolves_known_scope() -> None:
    assert substitute("{player}.name", {"player": "players.0"}) == "players.0.name"


def test_substitute_unknown_scope_raises() -> None:
    with pytest.raises(ValueError, match="unknown scope"):
        substitute("{player}.name", {})


def test_substitute_unterminated_brace_raises() -> None:
    with pytest.raises(ValueError, match="unterminated"):
        substitute("{player.name", {"player": "p"})


def test_is_reserved_namespace_aware() -> None:
    assert is_reserved("__inputs.title") is True
    assert is_reserved("__inputs") is True
    assert is_reserved("__inputstats.title") is False


def test_namespace_returns_first_segment() -> None:
    assert namespace("show.title") == "show"
    assert namespace("show") == "show"


def test_has_prefix_segment_aware() -> None:
    assert has_prefix("players.0.score", "players") is True
    assert has_prefix("playerstats.0", "players") is False
