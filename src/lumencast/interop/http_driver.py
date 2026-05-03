"""Harness-side bridge to a remote LSDP/1 server's test control plane."""

from __future__ import annotations

from typing import Any

from lumencast.conformance.scenario import Scenario


def canonical_interop_tokens() -> dict[str, str]:
    """Return the canonical ``$TOKEN_* → value`` map used by the interop matrix.

    Mirrored from
    ``lumencast-protocol/interop/fixtures/canonical-tokens.json`` so the
    CLI can default sanely without a runtime file dependency.
    """
    return {
        "$TOKEN_OPERATOR": "interop-tok-operator-7f3a",
        "$TOKEN_VIEWER": "interop-tok-viewer-7f3a",
        "$TOKEN_SERVICE": "interop-tok-service-7f3a",
        "$TOKEN_TEST": "interop-tok-test-7f3a",
        "$TOKEN_INVALID": "interop-tok-invalid-7f3a",
    }


class HTTPDriver:
    """Drive a remote LSDP/1 server through its ``/test/*`` HTTP endpoints.

    Implements the :class:`lumencast.conformance.harness.Driver` protocol.
    Construct with the control-plane URL and the canonical token map ;
    pass to :func:`lumencast.conformance.harness.run_scenarios`.
    """

    def __init__(
        self,
        control_url: str,
        tokens: dict[str, str] | None = None,
        *,
        timeout: float = 5.0,
    ) -> None:
        try:
            import httpx
        except ImportError as e:
            msg = (
                "lumencast.interop.HTTPDriver requires the [interop] extra: "
                'pip install "lumencast[interop]"'
            )
            raise ImportError(msg) from e

        self._control_url = control_url.rstrip("/")
        self._tokens = dict(tokens or canonical_interop_tokens())
        self._client = httpx.AsyncClient(timeout=timeout)
        self._closed = False

    async def aclose(self) -> None:
        """Release the underlying HTTP client. Safe to call multiple times."""
        if not self._closed:
            await self._client.aclose()
            self._closed = True

    async def __aenter__(self) -> HTTPDriver:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def health_check(self) -> None:
        """Verify the control plane is reachable and reports the expected version.

        Raises :class:`RuntimeError` on any mismatch so the harness fails
        fast instead of failing every scenario the same way.
        """
        resp = await self._client.get(f"{self._control_url}/test/health")
        if resp.status_code != 200:
            msg = f"health: HTTP {resp.status_code}"
            raise RuntimeError(msg)
        body = resp.json()
        if body.get("status") != "ok":
            msg = f"health: status={body.get('status')!r}"
            raise RuntimeError(msg)
        version = body.get("control_plane_version")
        if version != 1:
            msg = f"harness: control_plane_version={version}, want 1"
            raise RuntimeError(msg)

    async def setup(self, scenario_name: str, scenario: Scenario) -> tuple[str, dict[str, str]]:
        """Send ``POST /test/setup`` with the scenario's bundle + initial state."""
        body = {
            "scenario": scenario_name,
            "tokens": self._tokens,
            "bundles": _bundles_for(scenario),
            "initial_state": _extract_initial_state(scenario),
        }
        # Strip empties — see CONTROL.md robustness clause + Go HTTPDriver omitempty.
        body = {k: v for k, v in body.items() if v is not None}

        resp = await self._client.post(f"{self._control_url}/test/setup", json=body)
        if resp.status_code != 200:
            raise _problem_error(resp, "setup")
        sresp = resp.json()
        ws_url = sresp.get("ws_url")
        if not isinstance(ws_url, str) or not ws_url:
            msg = "harness: setup returned empty ws_url"
            raise RuntimeError(msg)
        return ws_url, dict(self._tokens)

    async def snapshot_state(self) -> dict[str, Any] | None:
        """Return the active scene state, or ``None`` on transport failure."""
        try:
            resp = await self._client.get(f"{self._control_url}/test/state")
        except Exception:
            return None
        if resp.status_code != 200:
            return None
        try:
            body = resp.json()
        except ValueError:
            return None
        state = body.get("state")
        return state if isinstance(state, dict) else None

    async def emit(self, patches: list[dict[str, Any]]) -> None:
        """Trigger a server-driven delta via ``POST /test/emit``."""
        resp = await self._client.post(
            f"{self._control_url}/test/emit",
            json={"patches": patches},
        )
        if resp.status_code != 204:
            raise _problem_error(resp, "emit")

    async def reset(self) -> None:
        """Optional pre-scenario teardown via ``POST /test/reset``."""
        resp = await self._client.post(f"{self._control_url}/test/reset")
        if resp.status_code != 204:
            raise _problem_error(resp, "reset")


def _bundles_for(sc: Scenario) -> list[dict[str, Any]]:
    """Map a scenario's declared bundles into the control-plane payload.

    Scenarios that omit bundles get a synthetic single-scene seed derived
    from the first ``server-sends`` snapshot — matching the Go reference.
    """
    if sc.bundles:
        out: list[dict[str, Any]] = []
        for b in sc.bundles:
            sid = b.id
            inline_sid = b.inline.get("scene_id") if isinstance(b.inline, dict) else None
            if isinstance(inline_sid, str) and inline_sid:
                sid = inline_sid
            out.append({"id": sid, "hash": b.hash, "inline": b.inline})
        return out

    sid, h = _first_scene_id_and_hash(sc)
    if not sid:
        sid = sc.name
    if not h:
        h = "sha256:0000000000000000000000000000000000000000000000000000000000000000"
    inline: dict[str, Any] = {}
    state = _extract_initial_state(sc) or {}
    inputs: list[dict[str, Any]] = []
    for path in state:
        if path.startswith("__inputs."):
            inputs.append({"path": path})
    if inputs:
        inline["operator_inputs"] = inputs
    return [{"id": sid, "hash": h, "inline": inline}]


def _first_scene_id_and_hash(sc: Scenario) -> tuple[str, str]:
    """Pull the first non-sentinel ``scene_id`` / ``scene_version`` from a server-sends step."""
    sid = ""
    h = ""
    for step in sc.steps:
        if step.kind.value != "server-sends":
            continue
        candidate_sid = step.frame.get("scene_id")
        if not sid and isinstance(candidate_sid, str) and candidate_sid not in {"", "$ANY"}:
            sid = candidate_sid
        candidate_hash = step.frame.get("scene_version")
        if not h and isinstance(candidate_hash, str) and candidate_hash not in {"", "$ANY_HASH"}:
            h = candidate_hash
        if sid and h:
            break
    return sid, h


def _extract_initial_state(sc: Scenario) -> dict[str, Any] | None:
    """Pull the ``state`` from the first server-sends snapshot.

    Stripping ``$ANY`` / ``$ANY_HASH`` sentinels — we cannot seed a server
    with literal sentinel values.
    """
    for step in sc.steps:
        if step.kind.value != "server-sends":
            continue
        if step.frame.get("type") != "snapshot":
            continue
        state = step.frame.get("state")
        if not isinstance(state, dict):
            return None
        out: dict[str, Any] = {}
        for k, v in state.items():
            if isinstance(v, str) and v in {"$ANY", "$ANY_HASH"}:
                continue
            out[k] = v
        return out
    return None


def _problem_error(resp: Any, op: str) -> RuntimeError:
    """Decode an RFC 7807 problem body into a readable error."""
    try:
        body = resp.json()
        detail = body.get("detail", "")
        return RuntimeError(f"harness: {op} HTTP {resp.status_code}: {detail}")
    except Exception:
        return RuntimeError(f"harness: {op} HTTP {resp.status_code}")
