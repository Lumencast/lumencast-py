"""Cross-language parity of the LSML content hash.

The hash is only useful if every SDK computes the same one for the same
bundle: adopt-on-verify compares a hash produced by one implementation
against a hash produced by another, and a divergence does not raise — it
silently falls back to a legacy identity, forever, with no signal.

Two oracles, neither of them this codebase's own output:

* ``testdata/number_canon.tsv`` — canonical rendering of float64 values,
  captured from Go ``encoding/json`` (whose float format is documented as
  ECMAScript-compatible, hence also the TS ``JSON.stringify`` form).
* the three ``@lumencast/compiler`` goldens already used by lumencast-go's
  ``TestHashBundle_CrossLanguageGolden`` — canonical bytes AND sha256
  captured from the TS reference implementation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lumencast.lsml import (
    canonicalise,
    format_number,
    hash_bundle,
    replace_scene_version,
)

_TESTDATA = Path(__file__).parent / "testdata" / "number_canon.tsv"


def _number_cases() -> list[tuple[str, str]]:
    cases: list[tuple[str, str]] = []
    for line in _TESTDATA.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        literal, canonical = line.split("\t")
        cases.append((literal, canonical))
    return cases


@pytest.mark.parametrize(("literal", "expected"), _number_cases())
def test_number_rendering_matches_go(literal: str, expected: str) -> None:
    """Every float64 renders exactly as Go (and therefore TS) renders it.

    The literal is read through ``json.loads`` rather than evaluated: that is
    the door a real bundle's numbers come through, so an ``int``/``float``
    distinction the parser makes is one the hash has to survive too.
    """
    assert format_number(json.loads(literal)) == expected


def test_large_integer_goes_through_float64() -> None:
    """An integer past float64's exact range loses precision — deliberately.

    Python could hold it exactly; TS and Go cannot, and the canonical form is
    defined by what all three agree on. Keeping Python's exact digits here is
    precisely the bug this module was written to fix.
    """
    assert format_number(1234567890123456789) == "1234567890123456800"


def test_integral_float_drops_its_fraction() -> None:
    assert format_number(2.0) == "2"
    assert json.loads("2.0") == 2.0  # YAML/JSON both hand us a float here


def test_short_exponent_is_not_zero_padded() -> None:
    """``1e-7``, never Python's ``1e-07``."""
    assert format_number(1e-7) == "1e-7"


def test_non_finite_has_no_canonical_form() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            format_number(value)


# --- TS goldens (identical fixtures to lumencast-go) ------------------------

_TS_GOLDENS = [
    (
        "case_a_float",
        '{"lsml":"1.1","scene_id":"s","scene_version":"sha256:00000000000000000000'
        '00000000000000000000000000000000000000000000","layout":{"kind":"stack"},'
        '"defaults":{"tiny":0.0000001,"exp":1.5e-10,"whole":2.0,"big":1234567890123456789}}',
        "16dee731508082b869796d77d45832e1d780866259ab48f5918e12c547c94662",
        '{"defaults":{"big":1234567890123456800,"exp":1.5e-10,"tiny":1e-7,"whole":2},'
        '"layout":{"kind":"stack"},"lsml":"1.1","scene_id":"s","scene_version":'
        '"sha256:0000000000000000000000000000000000000000000000000000000000000000"}',
    ),
    (
        "case_b_html",
        '{"lsml":"1.1","scene_id":"s","scene_version":"sha256:00000000000000000000'
        '00000000000000000000000000000000000000000000","layout":{"kind":"stack"},'
        '"metadata":{"title":"A & B <live>"}}',
        "7050dd0c6c1a92a174db87b457eb66205519cd87ac583694f97c8c3fb7da097c",
        '{"layout":{"kind":"stack"},"lsml":"1.1","metadata":{"title":"A & B <live>"},'
        '"scene_id":"s","scene_version":'
        '"sha256:0000000000000000000000000000000000000000000000000000000000000000"}',
    ),
    (
        "case_c_optional_absent",
        '{"lsml":"1.1","scene_id":"s","scene_version":"sha256:00000000000000000000'
        '00000000000000000000000000000000000000000000","layout":{"kind":"stack"}}',
        "f3f9db9b4436fe3ba31794e74d5c5959f94e90360c78d783adcd71989e2bd85c",
        '{"layout":{"kind":"stack"},"lsml":"1.1","scene_id":"s","scene_version":'
        '"sha256:0000000000000000000000000000000000000000000000000000000000000000"}',
    ),
]


@pytest.mark.parametrize(
    ("name", "raw", "ts_hash", "ts_canonical"),
    _TS_GOLDENS,
    ids=[case[0] for case in _TS_GOLDENS],
)
def test_matches_typescript_golden(name: str, raw: str, ts_hash: str, ts_canonical: str) -> None:
    """Canonical bytes AND hash match the TS reference, byte for byte.

    ``case_a_float`` is the one that used to fail: it carries a large integer,
    an integral float and a single-digit exponent — the three shapes where
    ``json.dumps`` and the reference serializers disagree.
    """
    bundle = json.loads(raw)
    assert canonicalise(replace_scene_version(bundle)) == ts_canonical
    assert hash_bundle(bundle) == ts_hash


def test_html_characters_are_not_escaped() -> None:
    """``&``, ``<``, ``>`` stay literal — the trap Go had to disable escaping for."""
    assert canonicalise({"t": "A & B <live>"}) == '{"t":"A & B <live>"}'
