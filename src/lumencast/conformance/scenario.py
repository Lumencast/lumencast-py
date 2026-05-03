"""YAML scenario loader.

Each scenario file under ``conformance/v1/scenarios/`` describes a
sequence of LSDP message exchanges and expected behaviours. This module
parses them into typed :class:`Scenario` objects ready for the player.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from lumencast.conformance.bundle_hash import hash_inline_bundle


class Tag(str, Enum):
    """Conformance importance level."""

    REQUIRED = "required"
    RECOMMENDED = "recommended"
    EXTENDED = "extended"


class Target(str, Enum):
    """Implementation under test for a scenario."""

    ANY = "any"
    SERVER = "server"
    RUNTIME = "runtime"


class StepKind(str, Enum):
    """Supported scenario step verbs."""

    CLIENT_SENDS = "client-sends"
    SERVER_SENDS = "server-sends"
    SERVER_EMITS = "server-emits"
    EXPECT_RUNTIME_STATE = "expect-runtime-state"
    EXPECT_SERVER_STATE = "expect-server-state"
    EXPECT_NO_FRAME_FOR = "expect-no-frame-for"
    EXPECT_CLIENT_ACTION = "expect-client-action"
    CLIENT_ACTION = "client-action"
    WAIT = "wait"
    SET_CLOCK = "set-clock"
    UNSUPPORTED = "__unsupported__"
    """Synthetic — assigned to step kinds the harness does not recognise."""


class ClientAction(str, Enum):
    """Verbs checked or driven by ``expect-client-action`` / ``client-action``."""

    CLOSE_WITH_REASON = "close-with-reason"
    RECONNECT = "reconnect"
    FETCH_BUNDLE = "fetch-bundle"
    STATUS_CHANGE = "status-change"
    ON_ERROR = "onError"
    SET_TOKEN = "setToken"
    DISCONNECT = "disconnect"


@dataclass(slots=True)
class BundleDecl:
    """One bundle declared on a scenario.

    ``inline`` carries the LSML body verbatim ; ``hash`` is computed at
    load-time from the canonical form (:data:`bundle_hash.ZERO_HASH` is
    substituted for ``scene_version`` during hashing).
    """

    id: str
    inline: dict[str, Any] = field(default_factory=dict)
    hash: str = ""


@dataclass(slots=True)
class Step:
    """One step in a scenario.

    Only the fields relevant to the step kind are populated.
    """

    kind: StepKind
    raw_kind: str = ""
    """Original ``kind`` string from YAML — preserved for unsupported steps."""
    frame: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    action: str = ""
    reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    """Extra fields the step kind may declare (e.g. ``token`` on ``client-action``)."""


@dataclass(slots=True)
class Scenario:
    """Parsed YAML scenario."""

    name: str
    description: str = ""
    tag: Tag = Tag.REQUIRED
    target: Target = Target.ANY
    spec_refs: list[str] = field(default_factory=list)
    bundles: list[BundleDecl] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    """Original YAML dict — used by the harness to inspect tokens / extras."""

    def bundle_hashes(self) -> dict[str, str]:
        """Return the precomputed ``id → hash`` map."""
        return {b.id: b.hash for b in self.bundles}


def parse_scenario(raw: bytes | str) -> Scenario:
    """Decode one YAML document into a :class:`Scenario` value.

    Computes inline bundle hashes eagerly so they are ready for
    placeholder substitution.
    """
    parsed = yaml.safe_load(raw)
    if not isinstance(parsed, dict):
        msg = "conformance: scenario root must be a mapping"
        raise ValueError(msg)

    name = parsed.get("name")
    if not isinstance(name, str) or not name:
        msg = "conformance: scenario missing 'name'"
        raise ValueError(msg)

    sc = Scenario(
        name=name,
        description=str(parsed.get("description", "")),
        tag=_parse_tag(parsed.get("tag")),
        target=_parse_target(parsed.get("target")),
        spec_refs=[str(r) for r in (parsed.get("spec_refs") or [])],
        bundles=_parse_bundles(parsed.get("bundles")),
        steps=_parse_steps(parsed.get("steps") or []),
        raw=parsed,
    )
    return sc


def load_scenarios(scenarios_dir: str | os.PathLike[str]) -> list[Scenario]:
    """Load every ``*.yaml`` file under ``scenarios_dir``."""
    base = Path(scenarios_dir)
    if not base.is_dir():
        msg = f"conformance: scenarios dir not found: {base}"
        raise FileNotFoundError(msg)
    out: list[Scenario] = []
    for path in sorted(base.glob("*.yaml")):
        raw = path.read_bytes()
        out.append(parse_scenario(raw))
    return out


def _parse_tag(value: Any) -> Tag:
    if value is None:
        return Tag.REQUIRED
    try:
        return Tag(str(value))
    except ValueError:
        return Tag.REQUIRED


def _parse_target(value: Any) -> Target:
    if value is None:
        return Target.ANY
    try:
        return Target(str(value))
    except ValueError:
        return Target.ANY


def _parse_bundles(raw: Any) -> list[BundleDecl]:
    if not isinstance(raw, list):
        return []
    out: list[BundleDecl] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        bid = str(item.get("id", ""))
        if not bid:
            continue
        inline = item.get("inline")
        inline_d = inline if isinstance(inline, dict) else {}
        h = hash_inline_bundle(inline_d) if inline_d else ""
        out.append(BundleDecl(id=bid, inline=inline_d, hash=h))
    return out


def _parse_steps(raw: Iterable[Any]) -> list[Step]:
    out: list[Step] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        kind_str = str(item.get("kind", ""))
        try:
            kind = StepKind(kind_str)
        except ValueError:
            # Open extension : unknown kinds become Unsupported variants —
            # only fail if the step actually runs.
            kind = StepKind.UNSUPPORTED
        step = Step(
            kind=kind,
            raw_kind=kind_str,
            frame=item.get("frame") or {},
            state=item.get("state") or {},
            duration_ms=int(item.get("duration_ms", 0) or 0),
            action=str(item.get("action", "")),
            reason=str(item.get("reason", "")),
        )
        # Stash any extra keys (e.g. ``token`` on ``client-action setToken``,
        # ``on_connection`` connection routing, ``mode`` on expect-state).
        known = {"kind", "frame", "state", "duration_ms", "action", "reason"}
        step.extra = {k: v for k, v in item.items() if k not in known}
        out.append(step)
    return out
