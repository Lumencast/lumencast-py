"""Bundle canonicalisation + hash determinism tests."""

from __future__ import annotations

from lumencast.conformance.bundle_hash import ZERO_HASH, hash_inline_bundle


def test_hash_deterministic_under_key_order() -> None:
    a = {"lsml": "1.0", "scene_id": "x", "layout": {"kind": "text"}}
    b = {"layout": {"kind": "text"}, "scene_id": "x", "lsml": "1.0"}
    assert hash_inline_bundle(a) == hash_inline_bundle(b)


def test_hash_replaces_scene_version() -> None:
    a = {"lsml": "1.0", "scene_id": "x", "scene_version": "sha256:abc", "layout": {}}
    b = {"lsml": "1.0", "scene_id": "x", "scene_version": ZERO_HASH, "layout": {}}
    assert hash_inline_bundle(a) == hash_inline_bundle(b)


def test_hash_format() -> None:
    h = hash_inline_bundle({"lsml": "1.0"})
    assert h.startswith("sha256:")
    assert len(h) == len("sha256:") + 64
