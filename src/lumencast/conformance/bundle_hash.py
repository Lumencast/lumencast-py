"""Canonical content hashing for LSML bundles.

Implements the LSML 1.0 § 3 canonicalisation rules :

1. UTF-8 encoding
2. Object keys sorted lexicographically at every nesting level
3. No insignificant whitespace
4. ``scene_version`` field replaced by the all-zero sha256 sentinel
   during the hash computation, then the result becomes the new
   ``scene_version``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

ZERO_HASH = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
"""Sentinel injected into ``scene_version`` during hashing."""


def hash_inline_bundle(inline: dict[str, Any]) -> str:
    """Return the canonical ``sha256:<hex>`` content hash of ``inline``.

    The input is not mutated. If ``scene_version`` is present in the
    bundle, it is replaced by :data:`ZERO_HASH` before hashing so the
    result is not self-referential.
    """
    prepared = _replace_scene_version(inline)
    canonical = _canonicalise(prepared)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _replace_scene_version(value: Any) -> Any:
    """Return a deep copy of ``value`` with top-level ``scene_version`` replaced."""
    if not isinstance(value, dict):
        return value
    out = {k: v for k, v in value.items()}
    if "scene_version" in out:
        out["scene_version"] = ZERO_HASH
    return out


def _canonicalise(value: Any) -> str:
    """Emit canonical JSON : sorted keys, tight separators, no extra whitespace."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
