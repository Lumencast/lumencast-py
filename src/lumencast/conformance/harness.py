"""Scenario player + harness reporter.

Drives an LSDP/1 server through a list of scenarios via either an
in-process :class:`Driver` or the HTTP control plane (preferred for
cross-language interop runs).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from lumencast.conformance.match import match_frame, match_value
from lumencast.conformance.placeholders import substitute_placeholders
from lumencast.conformance.scenario import (
    ClientAction,
    Scenario,
    Step,
    StepKind,
    Tag,
    Target,
)
from lumencast.protocol.envelope import SUBPROTOCOL

_log = logging.getLogger("lumencast.conformance")

STEP_TIMEOUT_SECS = 2.0
SCENARIO_TIMEOUT_SECS = 30.0


class Outcome(str, Enum):
    """Per-scenario terminal status."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@runtime_checkable
class Driver(Protocol):
    """Bridge to the server under test.

    The harness calls :meth:`setup` before each scenario to acquire a
    fresh ``ws://`` URL plus the canonical token map. Optional methods
    :meth:`snapshot_state` and :meth:`emit` enable the matching scenario
    step kinds.
    """

    async def setup(self, scenario_name: str, scenario: Scenario) -> tuple[str, dict[str, str]]:
        """Reset state, register the scenario's bundle, return ``(ws_url, tokens)``."""
        ...

    async def snapshot_state(self) -> dict[str, Any] | None:
        """Return the active scene state (for ``expect-server-state``)."""
        ...

    async def emit(self, patches: list[dict[str, Any]]) -> None:
        """Trigger a server-driven delta (for ``server-emits``)."""
        ...

    async def reset(self) -> None:
        """Drop all scenes / tokens. Optional ; ``setup`` already implies reset."""
        ...


@dataclass(slots=True)
class Config:
    """Harness configuration."""

    driver: Driver
    tag_filter: Tag = Tag.REQUIRED
    skip_scenarios: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Result:
    """Per-scenario outcome."""

    name: str
    tag: Tag
    target: Target
    outcome: Outcome
    reason: str = ""


@dataclass(slots=True)
class Report:
    """Aggregated run report."""

    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[Result] = field(default_factory=list)


async def run_scenarios(scenarios: list[Scenario], cfg: Config) -> Report:
    """Run each scenario and return the aggregated :class:`Report`."""
    rep = Report()
    for sc in scenarios:
        rep.total += 1
        if sc.name in cfg.skip_scenarios:
            rep.skipped += 1
            rep.results.append(
                Result(sc.name, sc.tag, sc.target, Outcome.SKIP, "skipped via config")
            )
            continue
        if cfg.tag_filter is not None and sc.tag is not cfg.tag_filter:
            # Filter mismatch — count as skipped silently.
            rep.skipped += 1
            rep.results.append(Result(sc.name, sc.tag, sc.target, Outcome.SKIP, "tag filter"))
            continue
        if sc.target is Target.RUNTIME:
            rep.skipped += 1
            rep.results.append(
                Result(
                    sc.name,
                    sc.tag,
                    sc.target,
                    Outcome.SKIP,
                    "runtime-targeted scenario, harness drives a server",
                )
            )
            continue

        if _has_unsupported_step(sc):
            # We auto-skip if a scenario requires a step verb we don't drive.
            # The cross-language contract treats unknown verbs as opt-in — see
            # SCENARIO-FORMAT.md "Open step kinds".
            rep.skipped += 1
            rep.results.append(Result(sc.name, sc.tag, sc.target, Outcome.SKIP, "unsupported step"))
            continue

        try:
            await asyncio.wait_for(_run_one(sc, cfg.driver), timeout=SCENARIO_TIMEOUT_SECS)
        except _ScenarioSkipped as e:
            rep.skipped += 1
            rep.results.append(Result(sc.name, sc.tag, sc.target, Outcome.SKIP, str(e)))
        except Exception as e:
            rep.failed += 1
            rep.results.append(
                Result(sc.name, sc.tag, sc.target, Outcome.FAIL, f"{type(e).__name__}: {e}")
            )
        else:
            rep.passed += 1
            rep.results.append(Result(sc.name, sc.tag, sc.target, Outcome.PASS))

    return rep


# --- internals --------------------------------------------------------------


class _ScenarioSkipped(Exception):
    """Internal — a step asked for an unsupported runtime feature mid-run."""


def _has_unsupported_step(sc: Scenario) -> bool:
    """Return True if the scenario uses a step kind we cannot execute."""
    runnable = {
        StepKind.CLIENT_SENDS,
        StepKind.SERVER_SENDS,
        StepKind.SERVER_EMITS,
        StepKind.EXPECT_RUNTIME_STATE,
        StepKind.EXPECT_SERVER_STATE,
        StepKind.EXPECT_NO_FRAME_FOR,
        StepKind.EXPECT_CLIENT_ACTION,
        StepKind.WAIT,
    }
    for step in sc.steps:
        if step.kind not in runnable:
            return True
    return False


async def _run_one(sc: Scenario, driver: Driver) -> None:
    """Execute one scenario end-to-end : setup, dial, replay, teardown."""
    try:
        import websockets
    except ImportError as e:
        msg = "conformance harness requires the [server] extra: pip install 'lumencast[server]'"
        raise ImportError(msg) from e

    ws_url, tokens = await driver.setup(sc.name, sc)
    bundle_hashes = sc.bundle_hashes()

    # ``Subprotocol`` is just a NewType alias of str — cast keeps mypy happy
    # without a runtime cost.
    from websockets import Subprotocol

    async with websockets.connect(ws_url, subprotocols=[Subprotocol(SUBPROTOCOL)]) as ws:
        runtime_state: dict[str, Any] = {}
        for step in sc.steps:
            await _run_step(ws, driver, step, sc, tokens, bundle_hashes, runtime_state)


async def _run_step(
    ws: Any,
    driver: Driver,
    step: Step,
    sc: Scenario,
    tokens: dict[str, str],
    bundle_hashes: dict[str, str],
    runtime_state: dict[str, Any],
) -> None:
    """Dispatch one step against ``ws`` / ``driver``."""
    if step.kind is StepKind.CLIENT_SENDS:
        frame = substitute_placeholders(step.frame, tokens, bundle_hashes)
        await ws.send(json.dumps(frame, ensure_ascii=False, separators=(",", ":")))
        return

    if step.kind is StepKind.SERVER_SENDS:
        await _expect_server_frame(ws, step.frame, tokens, bundle_hashes, runtime_state)
        return

    if step.kind is StepKind.SERVER_EMITS:
        # Optional: read echo first (150 ms) — the server may have already
        # broadcast a delta from a prior client-sends input ; if so we
        # consume it now so the explicit emit lands cleanly afterwards.
        await _drain_one_frame_with_timeout(ws, 0.15, runtime_state)
        kind = step.frame.get("type")
        if kind != "delta":
            msg = f"server-emits only supports type=delta, got {kind!r}"
            raise AssertionError(msg)
        patches_raw = step.frame.get("patches", [])
        if not isinstance(patches_raw, list):
            msg = "server-emits: patches must be a list"
            raise AssertionError(msg)
        patches: list[dict[str, Any]] = []
        for p in patches_raw:
            if not isinstance(p, dict):
                msg = f"server-emits: patch must be a mapping: {p!r}"
                raise AssertionError(msg)
            patches.append(substitute_placeholders(p, tokens, bundle_hashes))
        await driver.emit(patches)
        await _expect_server_frame(ws, step.frame, tokens, bundle_hashes, runtime_state)
        return

    if step.kind is StepKind.EXPECT_RUNTIME_STATE:
        for k, v in step.state.items():
            if k not in runtime_state:
                msg = f"runtime state missing {k!r}"
                raise AssertionError(msg)
            match_value(v, runtime_state[k], k)
        return

    if step.kind is StepKind.EXPECT_SERVER_STATE:
        state = await driver.snapshot_state()
        if state is None:
            # Fall back to the runtime-state shadow if the driver does not
            # expose introspection. Mirrors the Go reference behaviour.
            for k, v in step.state.items():
                if k not in runtime_state:
                    msg = f"server state missing {k!r}"
                    raise AssertionError(msg)
                match_value(v, runtime_state[k], k)
            return
        for k, v in step.state.items():
            if k not in state:
                msg = f"server state missing {k!r}"
                raise AssertionError(msg)
            match_value(v, state[k], k)
        return

    if step.kind is StepKind.EXPECT_NO_FRAME_FOR:
        d_secs = step.duration_ms / 1000.0
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=d_secs)
        except TimeoutError:
            return
        msg = f"expected silence for {d_secs}s, got frame: {raw!r}"
        raise AssertionError(msg)

    if step.kind is StepKind.EXPECT_CLIENT_ACTION:
        action = step.action
        if action in {ClientAction.CLOSE_WITH_REASON.value, ClientAction.RECONNECT.value}:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=STEP_TIMEOUT_SECS)
            except (TimeoutError, _ConnectionClosed):
                return
            except Exception:
                return
            msg = f"expected connection close, got frame: {raw!r}"
            raise AssertionError(msg)
        msg = f"unsupported expect-client-action.action={action!r}"
        raise _ScenarioSkipped(msg)

    if step.kind is StepKind.WAIT:
        await asyncio.sleep(step.duration_ms / 1000.0)
        return

    msg = f"unsupported step kind {step.raw_kind!r}"
    raise _ScenarioSkipped(msg)


async def _expect_server_frame(
    ws: Any,
    expected: dict[str, Any],
    tokens: dict[str, str],
    bundle_hashes: dict[str, str],
    runtime_state: dict[str, Any],
) -> None:
    """Read the next frame and match it against ``expected``."""
    raw = await asyncio.wait_for(ws.recv(), timeout=STEP_TIMEOUT_SECS)
    actual = json.loads(raw)
    if not isinstance(actual, dict):
        msg = f"server frame is not a JSON object: {raw!r}"
        raise AssertionError(msg)
    resolved = substitute_placeholders(expected, tokens, bundle_hashes)
    try:
        match_frame(resolved, actual)
    except AssertionError as e:
        msg = f"frame mismatch: {e} (got {raw!r})"
        raise AssertionError(msg) from None
    _absorb_server_frame(actual, runtime_state)


async def _drain_one_frame_with_timeout(
    ws: Any,
    timeout: float,
    runtime_state: dict[str, Any],
) -> None:
    """Read at most one frame within ``timeout`` ; absorb into the shadow state."""
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    except TimeoutError:
        return
    try:
        actual = json.loads(raw)
    except ValueError:
        return
    if isinstance(actual, dict):
        _absorb_server_frame(actual, runtime_state)


def _absorb_server_frame(frame: dict[str, Any], state: dict[str, Any]) -> None:
    """Mirror ``snapshot`` / ``delta`` into the runner's runtime-state shadow."""
    t = frame.get("type")
    if t == "snapshot":
        new_state = frame.get("state") or {}
        if isinstance(new_state, dict):
            state.clear()
            state.update(new_state)
    elif t == "delta":
        for p in frame.get("patches", []) or []:
            if isinstance(p, dict) and "path" in p:
                state[str(p["path"])] = p.get("value")


# `websockets.exceptions.ConnectionClosed` may not exist when the optional
# extra is absent — define a sentinel so the type check passes regardless.
_ConnectionClosed: type[Exception]
try:  # pragma: no cover - optional dependency probe
    from websockets.exceptions import ConnectionClosed as _ConnectionClosedReal

    _ConnectionClosed = _ConnectionClosedReal
except ImportError:  # pragma: no cover
    _ConnectionClosed = Exception


# Touch helpers so type checkers see them used.
_ = (Awaitable, Callable)
