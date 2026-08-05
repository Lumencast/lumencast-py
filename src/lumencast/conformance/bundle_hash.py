"""Canonical content hashing for LSML bundles — moved to :mod:`lumencast.lsml`.

Kept as a re-export so existing imports (and the conformance harness) keep
working. The implementation moved because it is not a test-harness concern:
the content hash is defined by LSML 1.0 § 3 and consumed by production
callers that address bundles by it.

The move also carried a fix. This module used ``json.dumps``, which renders
numbers the Python way — exact large integers, a trailing ``.0`` on integral
floats, zero-padded short exponents. The TS and Go reference serializers route
every number through float64 and render it per ECMAScript, so any bundle
carrying one of those shapes hashed differently here than everywhere else.
See :func:`lumencast.lsml.format_number`.
"""

from __future__ import annotations

from lumencast.lsml.hash import (
    ZERO_HASH,
    canonicalise,
    hash_inline_bundle,
    replace_scene_version,
)

#: Back-compat aliases for the previously private helpers.
_canonicalise = canonicalise
_replace_scene_version = replace_scene_version

__all__ = ["ZERO_HASH", "hash_inline_bundle"]
