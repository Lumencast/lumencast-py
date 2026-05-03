# lumencast-py

Python SDK and CLI for [Lumencast](https://github.com/Lumencast) — the LSDP/1 leaf-state delta protocol with LSML 1.0 scene bundles.

This is the canonical Python implementation of the Lumencast server kit, a fourth peer alongside the Go, TypeScript, and Rust SDKs. It speaks LSDP/1 verbatim and exposes the same `lumencast` CLI surface used in the cross-language interop matrix.

## Status

`v0.1.0` — initial release. LSDP/1 server side, LSML 1.0 codec and validator, conformance harness, interop control plane.

## Install

```sh
pip install "lumencast[server]"
```

The base package only ships the wire codec and the conformance scaffolding (no FastAPI / uvicorn). The `[server]` extra pulls in the runtime needed to expose an LSDP/1 WebSocket endpoint. The `[interop]` extra adds `httpx` for the cross-language harness.

## Quickstart — server

```python
import asyncio
from lumencast.server import Server, StaticTokens, Identity, Role

async def main() -> None:
    auth = StaticTokens({"my-op-token": Identity(subject="alice", role=Role.OPERATOR)})
    server = Server(auth=auth)

    scene = server.new_scene("main-stage")
    await scene.set({"score.home": 0, "score.away": 0})
    server.set_active("main-stage")

    await server.run(host="127.0.0.1", port=8080)

asyncio.run(main())
```

The runtime can connect to `ws://127.0.0.1:8080/lsdp.v1` with the operator token and receive snapshots and deltas.

## CLI

```sh
# Serve a scenario for cross-language interop runs.
python -m lumencast serve-scenario --ws-port 8081 --test-control-port 9000

# Drive a remote LSDP/1 server through the conformance suite.
python -m lumencast conformance \
    --server ws://127.0.0.1:8081/lsdp.v1 \
    --control-url http://127.0.0.1:9000

# Validate an LSML bundle.
python -m lumencast validate path/to/bundle.json

# Compute the canonical content hash of a bundle.
python -m lumencast build path/to/bundle.json
```

## Package matrix

| Module | Purpose |
|---|---|
| `lumencast.protocol` | Pure LSDP/1 wire codec — frames, sequencing, leaf-path validation, error taxonomy. No IO. |
| `lumencast.server` | FastAPI + WebSocket server kit — scenes, leaf-grain store, role enforcement, input validation. |
| `lumencast.interop` | Test control plane (`/test/*` HTTP endpoints) and HTTP driver (cross-language harness). |
| `lumencast.conformance` | YAML scenario loader, placeholder substitution, frame matcher, scenario player. |
| `lumencast.cli` | `python -m lumencast` entry point — `serve-scenario`, `conformance`, `validate`, `build`. |

## Spec references

- [LSDP/1 wire protocol](https://github.com/Lumencast/lumencast-protocol/blob/main/spec/LSDP-1.md)
- [LSML 1.0 scene format](https://github.com/Lumencast/lumencast-protocol/blob/main/spec/LSML-1.md)
- [Error code taxonomy](https://github.com/Lumencast/lumencast-protocol/blob/main/spec/ERROR-CODES.md)
- [Interop test control plane](https://github.com/Lumencast/lumencast-protocol/blob/main/interop/CONTROL.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Code, commits, branches, PRs, and technical documentation are written in English.

## License

Apache 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
