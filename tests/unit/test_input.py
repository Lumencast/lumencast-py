"""InputSpec constraint enforcement + inline parser tests."""

from __future__ import annotations

import pytest

from lumencast.server.input import InputSpec, check_constraint, parse_inline_specs


def test_string_max_length_passes() -> None:
    spec = InputSpec(path="x", type="string", max_length=10)
    assert check_constraint(spec, "hello") is None


def test_string_max_length_violates() -> None:
    spec = InputSpec(path="x", type="string", max_length=3)
    err = check_constraint(spec, "hello")
    assert err is not None and "exceeds" in err


def test_string_max_length_counts_chars_not_bytes() -> None:
    # 5 emoji chars (each multi-byte). Spec measures chars per LSML §8.
    spec = InputSpec(path="x", type="string", max_length=5)
    assert check_constraint(spec, "🎬🎬🎬🎬🎬") is None


def test_number_min_max() -> None:
    spec = InputSpec(path="x", type="number", min_value=0, max_value=10)
    assert check_constraint(spec, 5) is None
    assert check_constraint(spec, 11) is not None
    assert check_constraint(spec, -1) is not None


def test_number_rejects_bool() -> None:
    # bool is a subclass of int — must be rejected explicitly.
    spec = InputSpec(path="x", type="number")
    assert check_constraint(spec, True) is not None


def test_boolean_strict() -> None:
    spec = InputSpec(path="x", type="boolean")
    assert check_constraint(spec, True) is None
    assert check_constraint(spec, 1) is not None


def test_enum_membership() -> None:
    spec = InputSpec(path="x", type="enum", values=["a", "b"])
    assert check_constraint(spec, "a") is None
    assert check_constraint(spec, "c") is not None


def test_empty_type_passes_anything() -> None:
    spec = InputSpec(path="x", type="")
    assert check_constraint(spec, {"weird": "value"}) is None


def test_parse_inline_specs_nested_constraints() -> None:
    raw = [
        {
            "path": "show.title",
            "type": "string",
            "constraints": {"maxLength": 80},
        },
        {
            "path": "show.theme",
            "type": "enum",
            "values": ["dark", "light"],
        },
    ]
    specs = parse_inline_specs(raw)
    assert len(specs) == 2
    assert specs[0].path == "show.title"
    assert specs[0].max_length == 80
    assert specs[1].values == ["dark", "light"]


def test_parse_inline_specs_skips_invalid_items() -> None:
    raw = ["not a dict", {"path": ""}, {"no": "path"}]
    specs = parse_inline_specs(raw)
    assert specs == []


def test_parse_inline_specs_handles_empty_input() -> None:
    assert parse_inline_specs(None) == []
    assert parse_inline_specs([]) == []
    assert parse_inline_specs("not a list") == []


@pytest.mark.parametrize(
    ("min_value", "max_value", "value", "ok"),
    [
        (0, 10, 5, True),
        (0, 10, 0, True),
        (0, 10, 10, True),
        (0, 10, -0.001, False),
        (None, 10, -1000, True),
        (0, None, 1e9, True),
    ],
)
def test_number_bounds_inclusive(
    min_value: float | None, max_value: float | None, value: float, ok: bool
) -> None:
    spec = InputSpec(path="x", type="number", min_value=min_value, max_value=max_value)
    result = check_constraint(spec, value)
    assert (result is None) is ok
