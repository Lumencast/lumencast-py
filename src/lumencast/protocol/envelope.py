"""LSDP/1 envelope constants and JSON helpers.

The envelope is the outer ``{"v": 1, "type": "...", ...}`` shape every
LSDP/1 frame carries. This module owns :

- ``VERSION`` — the protocol major (always ``1`` in LSDP/1).
- ``SUBPROTOCOL`` — the WebSocket subprotocol tag (``lsdp.v1``, dot-form).
- ``encode_json`` / ``decode_json`` — the canonical text-frame round-trip.

Higher layers (codec, frames) build on these primitives.
"""

from __future__ import annotations

import json
from typing import Any

VERSION: int = 1
"""LSDP protocol major. Receivers MUST reject ``v != 1`` frames."""

SUBPROTOCOL: str = "lsdp.v1"
"""WebSocket subprotocol tag — dot-form per the spec § 1."""


def encode_json(value: Any) -> str:
    """Encode ``value`` to a compact, deterministic JSON text frame.

    Uses ``ensure_ascii=False`` so leaf paths containing ``<``, ``>``, ``&``
    pass through verbatim instead of being escaped, and a tight separator
    pair to match the byte-level conformance fixtures.
    """
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decode_json(raw: str | bytes) -> dict[str, Any]:
    """Parse ``raw`` as a JSON object envelope.

    Raises :class:`ValueError` on syntactically invalid JSON or on a
    top-level value that is not a JSON object (LSDP/1 envelopes are
    always objects per § 2).
    """
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        msg = f"protocol: envelope must be a JSON object, got {type(obj).__name__}"
        raise ValueError(msg)
    return obj
