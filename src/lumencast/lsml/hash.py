"""Canonical content hashing for LSML bundles (LSML 1.0 § 3).

Canonicalisation rules:

1. UTF-8 encoding
2. Object keys sorted lexicographically at every nesting level
3. No insignificant whitespace
4. ``scene_version`` replaced by the all-zero sha256 sentinel during the
   hash computation, so the result is not self-referential
5. Numbers rendered exactly as the reference serializers render them

Rule 5 is the one that is easy to get wrong, and getting it wrong is
silent: the hash simply differs from the one every other SDK computes for
the same bundle, and an adopt-on-verify path falls back to legacy forever
without ever reporting why.

``json.dumps`` does **not** implement it. Python preserves an ``int``
exactly, keeps the ``.0`` on an integral float, and pads short exponents
(``1e-07``); the TS reference (``@lumencast/compiler`` ``canonicalize.ts``,
via ``JSON.stringify``) and Go (``encoding/json``, which documents its
float format as ECMAScript-compatible) both route every number through
float64 and render it per ECMAScript ``Number::toString``. So
``1234567890123456789`` canonicalises to ``1234567890123456800``, ``2.0``
to ``2``, and ``1e-07`` to ``1e-7``.

:func:`format_number` implements that algorithm; ``testdata/number_canon.tsv``
pins it against output captured from Go.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any

ZERO_HASH = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
"""Sentinel injected into ``scene_version`` during hashing."""

#: Above this decimal position ECMAScript switches to exponential notation.
_EXP_UPPER = 21


def format_number(value: float | int) -> str:
    """Render a number exactly as the TS and Go serializers do.

    Every value goes through float64 first — that is what makes an integer
    beyond float64's exact range canonicalise to its nearest representable
    value, identically in all three SDKs, rather than to the digits Python
    happens to still hold.

    Raises :class:`ValueError` on a non-finite value: NaN and infinities have
    no JSON representation, and silently emitting ``NaN`` would produce a
    document no conforming parser accepts.
    """
    f = float(value)
    if math.isnan(f) or math.isinf(f):
        raise ValueError(f"{value!r} has no canonical JSON representation")
    # ECMAScript renders both zeros as "0" (JSON.stringify(-0) === "0").
    if f == 0.0:
        return "0"

    sign = "-" if f < 0 else ""
    digits, point = _shortest_digits(abs(f))
    count = len(digits)

    if count <= point <= _EXP_UPPER:
        return sign + digits + "0" * (point - count)
    if 0 < point <= _EXP_UPPER:
        return sign + digits[:point] + "." + digits[point:]
    if -6 < point <= 0:
        return sign + "0." + "0" * (-point) + digits

    exponent = point - 1
    mantissa = digits[0] + ("." + digits[1:] if count > 1 else "")
    return f"{sign}{mantissa}e{'+' if exponent >= 0 else '-'}{abs(exponent)}"


def _shortest_digits(value: float) -> tuple[str, int]:
    """Split a positive float into its shortest round-trip digits and scale.

    Returns ``(digits, point)`` such that the value equals
    ``0.<digits> * 10**point``. ``repr`` already yields the shortest string
    that round-trips (same guarantee as the TS and Go formatters), so the
    digits are read off it rather than recomputed — only their placement is
    re-derived, since Python and ECMAScript disagree on where to put the
    decimal point, never on which digits to print.
    """
    text = repr(value)
    if "e" in text:
        mantissa, exponent_text = text.split("e")
        exponent = int(exponent_text)
    else:
        mantissa, exponent = text, 0
    integer_part, _, fraction_part = mantissa.partition(".")

    raw = integer_part + fraction_part
    stripped = raw.lstrip("0")
    leading_zeros = len(raw) - len(stripped)
    digits = stripped.rstrip("0") or "0"
    return digits, len(integer_part) + exponent - leading_zeros


def canonicalise(value: Any) -> str:
    """Emit the canonical JSON form of ``value`` (LSML 1.0 § 3)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return format_number(value)
    if isinstance(value, str):
        # ensure_ascii=False keeps non-ASCII literal, and Python never escapes
        # & < > — the trap the Go SDK had to disable HTML escaping to avoid.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(canonicalise(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return (
            "{"
            + ",".join(
                json.dumps(str(key), ensure_ascii=False) + ":" + canonicalise(val)
                for key, val in sorted(value.items())
            )
            + "}"
        )
    raise TypeError(f"{type(value).__name__} has no canonical JSON form")


def canonical_bytes(bundle: Mapping[str, Any]) -> bytes:
    """Canonical UTF-8 bytes of ``bundle``, ``scene_version`` zeroed."""
    return canonicalise(replace_scene_version(bundle)).encode("utf-8")


def hash_bundle(bundle: Mapping[str, Any]) -> str:
    """Return the bare lowercase hex sha256 content address of ``bundle``.

    Bare, not ``sha256:``-prefixed: this is the form a content-addressed
    store keys by. :func:`hash_inline_bundle` returns the prefixed spelling
    that a bundle carries in its own ``scene_version``.
    """
    return hashlib.sha256(canonical_bytes(bundle)).hexdigest()


def hash_inline_bundle(inline: Mapping[str, Any]) -> str:
    """Return the ``sha256:<hex>`` content hash of ``inline``, unmutated."""
    return f"sha256:{hash_bundle(inline)}"


def replace_scene_version(value: Any) -> Any:
    """Shallow copy of ``value`` with a top-level ``scene_version`` zeroed."""
    if not isinstance(value, Mapping):
        return value
    out = dict(value)
    if "scene_version" in out:
        out["scene_version"] = ZERO_HASH
    return out
