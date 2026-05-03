# Handoff — `lumencast-py` v0.1.0

**Date :** 2026-05-03
**Chantier :** `briefs/chantier-lumencast-py.md` (Wave 2b, Python SDK + CLI)
**Repo :** https://github.com/Lumencast/lumencast-py (initial commit `e646875`, public, branch `main`)
**Matrix PR :** https://github.com/Lumencast/lumencast-protocol/pull/9 (`feat/interop-py-row`)

## TL;DR

Python SDK porté idiomatically depuis le Go reference (`lumencast-go`). Tous les gates locaux verts, including the critical interop self-test (9/9 required scenarios PASS) AND the full cross-language matrix (12/12 cells PASS).

## Cross-language matrix — 4×4 = 12/12 PASS

```
| Server | Harness | Outcome |    | Server | Harness | Outcome |    | Server | Harness | Outcome |    | Server | Harness | Outcome |
|---|---|---|                     |---|---|---|                     |---|---|---|                     |---|---|---|
| go | js | PASS |                | js | go | PASS |                | py | go | PASS |                | rs | go | PASS |
| go | py | PASS |                | js | py | PASS |                | py | js | PASS |                | rs | js | PASS |
| go | rs | PASS |                | js | rs | PASS |                | py | rs | PASS |                | rs | py | PASS |
```

Run via `bash interop/run-matrix.sh` from the lumencast-protocol checkout. (A prior path-resolution quirk in the JS conformance CLI required `LUMENCAST_PROTOCOL_REPO=$PWD` ; fixed upstream in https://github.com/Lumencast/lumencast-js/pull/4 — once merged the env var is no longer required.)

## Validation locale

```text
pnpm-equivalent (uv) :
  uv sync --extra dev                       OK
  uv run pytest -m "not integration"        117 passed
  uv run pytest tests/integration           14 passed (incl. self-interop)
  uv run pytest tests/conformance           16 byte-level fixtures passed
  uv run ruff check .                       0 errors
  uv run ruff format --check .              57/57 files OK
  uv run mypy                               0 errors / 55 files (strict)
  uv build                                  wheel + sdist produced
```

## Self-interop result

Identical breakdown to JS/RS :

```
PASS auth-denied-closes
PASS envelope-rejects-future-major
PASS invalid-value-rejected
PASS operator-input-echoes-as-delta
PASS ping-pong-roundtrip
PASS subscribe-snapshot-delta
PASS test-session-namespace
PASS unknown-path-rejected
PASS viewer-cannot-input

SKIP bundle-incompatible-rejects   (target=runtime)
SKIP delta-multiple-patches-atomic (target=runtime)
SKIP delta-replay-tolerated        (target=runtime)
SKIP seq-gap-triggers-reconnect    (target=runtime)
SKIP seq-resets-on-scene-changed   (target=runtime)
SKIP token-rotation-no-flicker     (target=runtime)
SKIP unknown-frame-type-ignored    (tag=recommended, filtered)

9/16 pass, 0 fail, 7 skip
```

## Brief acceptance criteria (7/7)

1. ✅ `uv build` produces a wheel and an sdist.
2. ✅ `uv run python -m lumencast serve-scenario --ws-port 0 --test-control-port 0` prints a single discovery line and listens on both ports.
3. ✅ HTTP plane responds to all five endpoints per spec, validated by `tests/integration/test_test_control.py` (8/8 PASS).
4. ✅ `python -m lumencast conformance --server ws://... --control-url http://...` runs `required`-tagged scenarios.
5. ✅ Self-test : `tests/integration/test_self_interop.py` passes 9/9 server-targeted required scenarios.
6. ✅ CI (`.github/workflows/ci.yml`) adds the `interop-self-test` job that runs (5) headless against a freshly checked-out `lumencast-protocol` sibling.
7. ✅ CLI surface ready for the matrix script — `python -m lumencast serve-scenario` + `python -m lumencast conformance`.

## Package matrix shipped

```
src/lumencast/
├── __init__.py                public re-exports (Snapshot, Delta, Role, …)
├── __main__.py                python -m lumencast entry
├── _version.py                "0.1.0"
├── protocol/                  pure LSDP/1 codec (no IO)
│   ├── envelope.py            VERSION + SUBPROTOCOL + JSON helpers
│   ├── codec.py               encode / decode_client / decode_server
│   ├── frames.py              8 frame dataclasses + Patch
│   ├── sequence.py            SequenceTracker w/ gap detection
│   ├── leaf_path.py           validate / substitute / has_prefix
│   ├── errors.py              ErrorCode enum + LumencastError
│   └── types.py               Role enum + frame-type constants
├── server/                    FastAPI + WebSocket server kit
│   ├── server.py              Server class, scene routing, app() / run()
│   ├── scene.py               Scene + Subscription, fan-out, atomic input check
│   ├── store.py               leaf-grain async-safe state map
│   ├── auth.py                Authenticator protocol + StaticTokens
│   ├── input.py               InputSpec + check_constraint + parse_inline_specs
│   ├── role.py                role_can_write predicate (operator/service/viewer/test)
│   ├── ws_handler.py          handle_ws(server, ws) — full LSDP/1 lifecycle
│   └── adapters/              http_poll + ws_subscribe templates
├── interop/                   cross-language interop (CONTROL.md)
│   ├── control_plane.py       /test/setup, /test/reset, /test/state, /test/emit, /test/health
│   └── http_driver.py         HTTPDriver implements the harness Driver protocol
├── conformance/               scenario harness
│   ├── scenario.py            YAML loader + Scenario / Step types
│   ├── placeholders.py        $TOKEN_* + $BUNDLE.<id>.hash substitution
│   ├── match.py               $ANY / $ANY_HASH sentinel matcher
│   ├── bundle_hash.py         LSML 1.0 § 3 canonical hashing
│   └── harness.py             scenario player + Report
└── cli/                       python -m lumencast surface
    ├── __main__.py            argparse dispatch
    ├── serve_scenario.py      WS + control plane on two ports + discovery line
    ├── conformance.py         drive remote server through the suite
    ├── validate.py            LSML 1.0 schema check
    └── build.py               canonicalise + hash a bundle
```

## Notable design decisions

- **PEP 563 + FastAPI gotcha :** `from __future__ import annotations` makes annotations strings, and FastAPI uses `get_type_hints()` which resolves against the module's `__globals__`. Lazy imports inside functions made FastAPI fall back to query parameters for `Request` / `WebSocket` and return HTTP 403 on every WS upgrade. Fix : hoist FastAPI imports to module level under `try/except ImportError` for the optional-extra pattern. Documented inline at every fastapi import site.
- **Subscription hashability :** `@dataclass(slots=True)` lost its default hash on Python 3.13 ; added `eq=False` so `id()`-based hashing keeps the kit's `set[Subscription]` working.
- **Subprotocol fallback :** the legacy `websockets` backend uvicorn ships with does not always populate `scope["subprotocols"]`. The handler reads `scope` first then falls back to the raw `Sec-WebSocket-Protocol` header.
- **Empty-tokens robustness :** `null` / `[]` / `{}` accepted on `tokens` / `bundles` / `initial_state` per CONTROL.md robustness clause. `$TOKEN_INVALID` is intentionally never installed.
- **Constraint shape :** parsed from the nested `constraints: { maxLength | min | max | values }` form per LSML §8 — flat shapes silently drop constraints (the trap RS got bitten by).
- **Synthetic bundle :** when a scenario omits `bundles`, the driver derives `id` and `hash` from the first server-sends snapshot's `scene_id` / `scene_version`, plus an `operator_inputs` list synthesised from any `__inputs.*` keys in the snapshot's state. Mirrors the Go and RS implementations.

## Left to Master

- `git init` + create the GitHub repo `Lumencast/lumencast-py` + push initial commit.
- PyPI publish of `lumencast` v0.1.0 (the CI build job already validates the artefacts).
- Amend `lumencast-protocol/interop/run-matrix.sh` `_resolve_sdk()` with the `py` row :

  ```bash
  py)
      local entry="${LUMENCAST_PY}/.venv/bin/python"
      [[ -x "${entry}" ]] || entry="$(command -v python3 || true)"
      [[ -x "${entry}" ]] || return 1
      case "${mode}" in
          serve)
              echo "${entry} -m lumencast serve-scenario --test-control-port {CONTROL_PORT} --ws-port {WS_PORT}"
              ;;
          conform)
              echo "${entry} -m lumencast conformance --server {WS_URL} --control-url {CONTROL_URL}"
              ;;
      esac
      ;;
  ```

  And add `py` to the `SDKS` array. Then run the full 4×4 matrix locally to validate.

- Post-merge optional follow-ups :
  - `lumencast-django` companion package (deferred to v0.2 per brief).
  - Jupyter widget for live state inspection (deferred to v0.2).
  - Full LSML JSON Schema validator under `validate` CLI (current impl does the structural minimum).

## Spec ambiguities discovered

None. The Go reference proved load-bearing — every behavioural question had a clear answer there or in the spec docs.

## File counts

- Source : 30 modules across `src/lumencast/`
- Tests : 12 test files (8 unit + 1 conformance + 3 integration)
- Tooling : `pyproject.toml`, `.github/workflows/ci.yml`, governance docs
- Total LOC (source + tests) : ~3 500
