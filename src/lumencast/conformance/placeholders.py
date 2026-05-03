"""Placeholder substitution for scenario frames.

Two placeholder families :

- ``$TOKEN_*`` — replaced from the canonical token map.
- ``$BUNDLE.<id>.hash`` — replaced from the per-scenario bundle hash map.

Unknown placeholders pass through verbatim so scenarios that intentionally
exercise rejection (``$TOKEN_INVALID``) still hit the server with the
literal token value supplied to the harness.
"""

from __future__ import annotations

from typing import Any


def substitute_placeholders(
    value: Any,
    tokens: dict[str, str],
    bundle_hashes: dict[str, str],
) -> Any:
    """Return a deep-copied ``value`` with placeholders substituted."""
    if isinstance(value, str):
        if value.startswith("$TOKEN_"):
            return tokens.get(value, value)
        if value.startswith("$BUNDLE.") and value.endswith(".hash"):
            bundle_id = value[len("$BUNDLE.") : -len(".hash")]
            return bundle_hashes.get(bundle_id, value)
        return value
    if isinstance(value, dict):
        return {k: substitute_placeholders(v, tokens, bundle_hashes) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute_placeholders(v, tokens, bundle_hashes) for v in value]
    return value
