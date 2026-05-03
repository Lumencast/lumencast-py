"""``lumencast conformance`` — drive a remote LSDP/1 server through the suite."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from lumencast.conformance.harness import Config, run_scenarios
from lumencast.conformance.scenario import Scenario, Tag, load_scenarios
from lumencast.interop.http_driver import HTTPDriver, canonical_interop_tokens


async def run(argv: Sequence[str]) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="lumencast conformance")
    parser.add_argument("--server", help="ws://host:port/lsdp.v1 endpoint of the server under test")
    parser.add_argument(
        "--control-url",
        required=True,
        help="http://host:port endpoint of the test control plane",
    )
    parser.add_argument("--scenarios", help="path to the scenarios directory")
    parser.add_argument(
        "--tag", default="required", help="scenario tag filter (required | recommended | extended)"
    )
    parser.add_argument(
        "--scenario", default="", help="run one named scenario only (no .yaml suffix)"
    )
    args = parser.parse_args(argv)

    scenarios_dir = _resolve_scenarios_dir(args.scenarios)
    if scenarios_dir is None:
        print(
            "lumencast conformance: cannot locate scenarios. Pass --scenarios DIR or set "
            "LUMENCAST_PROTOCOL_REPO to the lumencast-protocol checkout.",
            file=sys.stderr,
        )
        return 2

    try:
        all_scenarios = load_scenarios(scenarios_dir)
    except FileNotFoundError as e:
        print(f"lumencast conformance: {e}", file=sys.stderr)
        return 2

    selected: list[Scenario]
    if args.scenario:
        selected = [s for s in all_scenarios if s.name == args.scenario]
        if not selected:
            print(f"lumencast conformance: scenario {args.scenario!r} not found", file=sys.stderr)
            return 2
    else:
        selected = list(all_scenarios)

    try:
        tag_filter = Tag(args.tag)
    except ValueError:
        print(f"lumencast conformance: invalid --tag {args.tag!r}", file=sys.stderr)
        return 2

    async with HTTPDriver(args.control_url, canonical_interop_tokens()) as driver:
        try:
            await driver.health_check()
        except Exception as e:
            print(f"lumencast conformance: control plane unreachable: {e}", file=sys.stderr)
            return 1

        cfg = Config(driver=driver, tag_filter=tag_filter)
        report = await run_scenarios(selected, cfg)

    for r in report.results:
        line = f"{r.outcome.value:<4} {r.name}"
        if r.reason and r.outcome.value != "PASS":
            line += f"  ({r.reason})"
        print(line, file=sys.stderr)

    print(
        f"\n{report.passed}/{report.total} pass, {report.failed} fail, {report.skipped} skip",
        file=sys.stderr,
    )
    return 0 if report.failed == 0 else 1


def _resolve_scenarios_dir(explicit: str | None) -> str | None:
    """Locate the scenarios directory.

    Order of resolution :
    1. ``--scenarios`` flag.
    2. ``$LUMENCAST_PROTOCOL_REPO/conformance/v1/scenarios``.
    3. Sibling checkout : ``../lumencast-protocol/conformance/v1/scenarios``.
    """
    if explicit:
        return explicit
    env = os.environ.get("LUMENCAST_PROTOCOL_REPO")
    if env:
        candidate = Path(env) / "conformance" / "v1" / "scenarios"
        if candidate.is_dir():
            return str(candidate)
    sibling = Path.cwd().parent / "lumencast-protocol" / "conformance" / "v1" / "scenarios"
    if sibling.is_dir():
        return str(sibling)
    return None
