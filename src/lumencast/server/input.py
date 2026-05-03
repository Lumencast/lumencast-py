"""Operator input declaration + constraint enforcement (LSML 1.0 § 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InputSpec:
    """Description of one operator-controllable path and its constraints.

    Mirrors LSML 1.0 § 8. ``type`` values : ``string``, ``number``,
    ``boolean``, ``enum``, ``color``, ``date``, ``time``, ``path-ref``,
    ``image-ref``. Empty type skips type checking but still enforces
    declaredness.
    """

    path: str
    type: str = ""
    max_length: int | None = None
    """Applies to ``string`` only — chars, not bytes (per spec)."""

    min_value: float | None = None
    """Applies to ``number`` only."""

    max_value: float | None = None
    """Applies to ``number`` only."""

    values: list[str] = field(default_factory=list)
    """Enum domain for ``type == "enum"``."""


def check_constraint(spec: InputSpec, value: Any) -> str | None:
    """Validate ``value`` against ``spec``.

    Returns ``None`` when the value passes, or a human-readable error
    message describing the violation. Untyped specs (empty ``type``)
    pass any value — declaredness is enforced separately by the scene.
    """
    if not spec.type:
        return None
    t = spec.type
    if t == "string":
        if not isinstance(value, str):
            return f"expected string, got {type(value).__name__}"
        if spec.max_length is not None and len(value) > spec.max_length:
            return f"string length {len(value)} exceeds maxLength {spec.max_length}"
        return None
    if t == "number":
        # JSON numbers decode to int or float in Python ; bool is a subclass
        # of int so we explicitly reject it.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"expected number, got {type(value).__name__}"
        n = float(value)
        if spec.min_value is not None and n < spec.min_value:
            return f"number {n} below min {spec.min_value}"
        if spec.max_value is not None and n > spec.max_value:
            return f"number {n} above max {spec.max_value}"
        return None
    if t == "boolean":
        if not isinstance(value, bool):
            return f"expected boolean, got {type(value).__name__}"
        return None
    if t == "enum":
        if not isinstance(value, str):
            return f"expected enum string, got {type(value).__name__}"
        if value not in spec.values:
            return f"value {value!r} not in enum domain {spec.values!r}"
        return None
    return None


def parse_inline_specs(operator_inputs: Any) -> list[InputSpec]:
    """Parse an LSML inline ``operator_inputs`` list into :class:`InputSpec` records.

    Tolerant : unknown shapes are skipped. The nested ``constraints``
    object form (per LSML §8) is expected — flat shapes silently drop
    constraints (this is the trap RS got bitten by).
    """
    if not isinstance(operator_inputs, list):
        return []
    out: list[InputSpec] = []
    for item in operator_inputs:
        if not isinstance(item, dict):
            continue
        spec = InputSpec(
            path=str(item.get("path", "")),
            type=str(item.get("type", "")),
        )
        if not spec.path:
            continue
        constraints = item.get("constraints")
        if isinstance(constraints, dict):
            ml = constraints.get("maxLength")
            if isinstance(ml, int) and not isinstance(ml, bool):
                spec.max_length = ml
            elif isinstance(ml, float):
                spec.max_length = int(ml)
            mn = constraints.get("min")
            if isinstance(mn, (int, float)) and not isinstance(mn, bool):
                spec.min_value = float(mn)
            mx = constraints.get("max")
            if isinstance(mx, (int, float)) and not isinstance(mx, bool):
                spec.max_value = float(mx)
            vals = constraints.get("values")
            if isinstance(vals, list):
                spec.values = [str(v) for v in vals]
        # LSML also lets "values" hang directly off the operator_input
        # for enum types ; honour both forms.
        vals_top = item.get("values")
        if isinstance(vals_top, list) and not spec.values:
            spec.values = [str(v) for v in vals_top]
        out.append(spec)
    return out
