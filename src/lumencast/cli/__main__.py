"""Top-level dispatch for ``python -m lumencast``."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch to the right subcommand. Returns a process exit code."""
    parser = argparse.ArgumentParser(
        prog="lumencast",
        description="Lumencast Python SDK + CLI",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser(
        "serve-scenario", help="serve LSDP/1 with the interop test control plane", add_help=False
    )
    sub.add_parser(
        "conformance", help="run conformance scenarios against a remote server", add_help=False
    )
    sub.add_parser(
        "validate", help="validate an LSML bundle against the 1.0 schema", add_help=False
    )
    sub.add_parser("build", help="canonicalise and hash an LSML bundle", add_help=False)

    args, rest = parser.parse_known_args(argv if argv is not None else sys.argv[1:])

    if args.cmd == "serve-scenario":
        from lumencast.cli.serve_scenario import run as serve_run

        return asyncio.run(serve_run(rest))
    if args.cmd == "conformance":
        from lumencast.cli.conformance import run as conf_run

        return asyncio.run(conf_run(rest))
    if args.cmd == "validate":
        from lumencast.cli.validate import run as validate_run

        return validate_run(rest)
    if args.cmd == "build":
        from lumencast.cli.build import run as build_run

        return build_run(rest)

    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
