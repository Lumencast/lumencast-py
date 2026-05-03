"""LSDP/1 conformance harness — scenario loader, matcher, player.

The harness drives a remote LSDP/1 server through the standard scenario
suite shipped at ``lumencast-protocol/conformance/v1/scenarios``. It
mirrors the Go reference impl behaviour, including the synthetic-bundle
fallback and the runtime-target SKIP outcome.
"""

from __future__ import annotations

from lumencast.conformance.bundle_hash import hash_inline_bundle
from lumencast.conformance.harness import (
    Config,
    Outcome,
    Report,
    Result,
    run_scenarios,
)
from lumencast.conformance.match import (
    SENTINEL_ANY,
    SENTINEL_ANY_HASH,
    match_frame,
    match_value,
)
from lumencast.conformance.placeholders import substitute_placeholders
from lumencast.conformance.scenario import (
    BundleDecl,
    ClientAction,
    Scenario,
    Step,
    StepKind,
    Tag,
    Target,
    load_scenarios,
    parse_scenario,
)

__all__ = [
    "SENTINEL_ANY",
    "SENTINEL_ANY_HASH",
    "BundleDecl",
    "ClientAction",
    "Config",
    "Outcome",
    "Report",
    "Result",
    "Scenario",
    "Step",
    "StepKind",
    "Tag",
    "Target",
    "hash_inline_bundle",
    "load_scenarios",
    "match_frame",
    "match_value",
    "parse_scenario",
    "run_scenarios",
    "substitute_placeholders",
]
