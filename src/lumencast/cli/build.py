"""``lumencast build`` — canonicalise + content-hash a bundle in place."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from lumencast.conformance.bundle_hash import hash_inline_bundle


def run(argv: Sequence[str]) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="lumencast build")
    parser.add_argument("path", help="path to the LSML JSON bundle to canonicalise")
    parser.add_argument("--out", help="write canonical JSON to this path (default: stdout)")
    args = parser.parse_args(argv)

    p = Path(args.path)
    if not p.is_file():
        print(f"lumencast build: not a file: {p}", file=sys.stderr)
        return 2

    try:
        bundle = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"lumencast build: cannot read {p}: {e}", file=sys.stderr)
        return 2
    if not isinstance(bundle, dict):
        print("lumencast build: bundle root must be a JSON object", file=sys.stderr)
        return 1

    digest = hash_inline_bundle(bundle)
    bundle["scene_version"] = digest
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    if args.out:
        Path(args.out).write_text(canonical, encoding="utf-8")
        print(digest)
    else:
        print(canonical)
    return 0
