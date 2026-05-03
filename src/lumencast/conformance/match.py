"""Frame matcher with sentinel support.

Compares an expected frame template (from the scenario YAML) against an
actual frame received over the wire. Non-deterministic fields use
``$ANY`` / ``$ANY_HASH`` placeholders. Unknown fields in the actual
frame are tolerated (forward compat). Missing required fields fail.
"""

from __future__ import annotations

import re
from typing import Any

SENTINEL_ANY = "$ANY"
SENTINEL_ANY_HASH = "$ANY_HASH"

_SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def match_frame(expected: dict[str, Any], actual: dict[str, Any]) -> None:
    """Validate ``actual`` matches ``expected``.

    Raises :class:`AssertionError` on mismatch with a precise field path
    in the message.
    """
    for key, want in expected.items():
        if key not in actual:
            msg = f"missing field {key!r}"
            raise AssertionError(msg)
        match_value(want, actual[key], key)


def match_value(expected: Any, actual: Any, path: str) -> None:
    """Recursive match. See :func:`match_frame` for the rules."""
    if isinstance(expected, str):
        if expected == SENTINEL_ANY:
            return
        if expected == SENTINEL_ANY_HASH:
            if not isinstance(actual, str) or not _SHA256_RE.match(actual):
                msg = f"{path}: not a sha256 hash: {actual!r}"
                raise AssertionError(msg)
            return
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            msg = f"{path}: want mapping, got {type(actual).__name__}"
            raise AssertionError(msg)
        for k, v in expected.items():
            if k not in actual:
                msg = f"{path}.{k}: missing"
                raise AssertionError(msg)
            match_value(v, actual[k], f"{path}.{k}")
        return
    if isinstance(expected, list):
        if not isinstance(actual, list):
            msg = f"{path}: want list, got {type(actual).__name__}"
            raise AssertionError(msg)
        if len(actual) != len(expected):
            msg = f"{path}: length {len(actual)} != {len(expected)}"
            raise AssertionError(msg)
        for i, want in enumerate(expected):
            match_value(want, actual[i], f"{path}[{i}]")
        return
    if not _equal_scalar(expected, actual):
        msg = (
            f"{path}: want {expected!r} ({type(expected).__name__}), "
            f"got {actual!r} ({type(actual).__name__})"
        )
        raise AssertionError(msg)


def _equal_scalar(want: Any, got: Any) -> bool:
    """Numeric-tower-aware equality. Handles YAML int vs JSON float drift.

    Booleans are NOT numeric — we explicitly reject ``int(True) == 1``
    style coercions to keep type checks tight.
    """
    if isinstance(want, bool) or isinstance(got, bool):
        return bool(want == got and isinstance(want, bool) == isinstance(got, bool))
    wf, wok = _to_float(want)
    gf, gok = _to_float(got)
    if wok and gok:
        return wf == gf
    return bool(want == got)


def _to_float(value: Any) -> tuple[float, bool]:
    if isinstance(value, bool):
        return (0.0, False)
    if isinstance(value, (int, float)):
        return (float(value), True)
    return (0.0, False)
