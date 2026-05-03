"""``lumencast validate`` — basic LSML 1.0 schema check.

The rich validator (allowed-host enforcement, animation discipline, full
JSON Schema check) lives upstream in ``lumencast-protocol``. This CLI
performs the structural minimum so callers can sanity-check a bundle
they're about to publish.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def run(argv: Sequence[str]) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="lumencast validate")
    parser.add_argument("path", help="path to the LSML JSON bundle to validate")
    args = parser.parse_args(argv)

    p = Path(args.path)
    if not p.is_file():
        print(f"lumencast validate: not a file: {p}", file=sys.stderr)
        return 2

    try:
        bundle = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"lumencast validate: cannot read {p}: {e}", file=sys.stderr)
        return 2

    errors = list(_validate(bundle))
    if errors:
        for err in errors:
            print(f"lumencast validate: {err}", file=sys.stderr)
        return 1
    print(f"{p}: OK")
    return 0


def _validate(bundle: Any) -> list[str]:
    """Return a list of human-readable error messages (empty = valid)."""
    errs: list[str] = []
    if not isinstance(bundle, dict):
        return ["bundle root must be a JSON object"]
    if bundle.get("lsml") not in {"1.0", "1"}:
        errs.append(f"unsupported lsml version: {bundle.get('lsml')!r} (expected '1.0')")
    for required in ("scene_id", "scene_version", "layout"):
        if required not in bundle:
            errs.append(f"missing required field {required!r}")
    layout = bundle.get("layout")
    if layout is not None and not isinstance(layout, dict):
        errs.append("layout must be a JSON object (the root primitive)")
    if isinstance(layout, dict):
        kind = layout.get("kind")
        if kind not in {"stack", "grid", "frame", "text", "image", "shape", "media", "repeat"}:
            errs.append(f"layout.kind {kind!r} is not one of the 8 LSML 1.0 primitives")
    op_inputs = bundle.get("operator_inputs")
    if op_inputs is not None:
        if not isinstance(op_inputs, list):
            errs.append("operator_inputs must be a JSON array")
        else:
            for i, item in enumerate(op_inputs):
                if not isinstance(item, dict):
                    errs.append(f"operator_inputs[{i}] must be an object")
                    continue
                for required in ("path", "label", "type", "writable_by"):
                    if required not in item:
                        errs.append(f"operator_inputs[{i}] missing {required!r}")
    return errs
