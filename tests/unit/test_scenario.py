"""Scenario YAML loader tests."""

from __future__ import annotations

import textwrap

import pytest

from lumencast.conformance.scenario import (
    StepKind,
    Tag,
    Target,
    parse_scenario,
)


def test_minimal_scenario() -> None:
    raw = textwrap.dedent("""
        name: hello
        description: trivial
        tag: required
        target: server
        steps:
          - kind: client-sends
            frame:
              v: 1
              type: subscribe
              token: $TOKEN_OPERATOR
    """)
    sc = parse_scenario(raw)
    assert sc.name == "hello"
    assert sc.tag is Tag.REQUIRED
    assert sc.target is Target.SERVER
    assert len(sc.steps) == 1
    assert sc.steps[0].kind is StepKind.CLIENT_SENDS


def test_unknown_step_kind_marks_unsupported() -> None:
    raw = textwrap.dedent("""
        name: future
        description: x
        tag: required
        target: any
        steps:
          - kind: future-verb
            payload: 42
    """)
    sc = parse_scenario(raw)
    assert sc.steps[0].kind is StepKind.UNSUPPORTED
    assert sc.steps[0].raw_kind == "future-verb"


def test_inline_bundle_hash_computed() -> None:
    raw = textwrap.dedent("""
        name: with-bundle
        description: x
        tag: required
        target: server
        bundles:
          - id: scoreboard
            inline:
              lsml: "1.0"
              scene_id: scoreboard
              scene_version: sha256:0000000000000000000000000000000000000000000000000000000000000000
              layout:
                kind: text
                bind:
                  value: title
        steps: []
    """)
    sc = parse_scenario(raw)
    assert len(sc.bundles) == 1
    assert sc.bundles[0].hash.startswith("sha256:")
    assert len(sc.bundles[0].hash) == len("sha256:") + 64


def test_default_target_is_any_and_tag_is_required() -> None:
    raw = textwrap.dedent("""
        name: defaults
        description: x
        steps: []
    """)
    sc = parse_scenario(raw)
    assert sc.target is Target.ANY
    assert sc.tag is Tag.REQUIRED


def test_missing_name_rejected() -> None:
    raw = textwrap.dedent("""
        description: x
        steps: []
    """)
    with pytest.raises(ValueError):
        parse_scenario(raw)
