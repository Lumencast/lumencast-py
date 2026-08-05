"""LSML bundle canonicalisation and content hashing (LSML 1.0 § 3).

The public home of the content hash. It previously lived under
``lumencast.conformance``, which said "test harness" about a function the
protocol itself defines; that module now re-exports from here.
"""

from lumencast.lsml.hash import (
    ZERO_HASH,
    canonical_bytes,
    canonicalise,
    format_number,
    hash_bundle,
    hash_inline_bundle,
    replace_scene_version,
)

__all__ = [
    "ZERO_HASH",
    "canonical_bytes",
    "canonicalise",
    "format_number",
    "hash_bundle",
    "hash_inline_bundle",
    "replace_scene_version",
]
