# Security Policy

## Reporting a vulnerability

Please do not file public GitHub issues for security-sensitive bugs in `lumencast-py`. Instead, email the maintainers privately at `security@lumencast.dev` (or open a GitHub Security Advisory on this repository if email is unavailable).

We aim to respond within 72 hours and will coordinate disclosure with you. Patches for confirmed vulnerabilities are released as patch versions (e.g. `0.1.x`) on PyPI.

## Scope

In scope :

- The LSDP/1 wire codec — any input that triggers crashes, infinite loops, unbounded memory, or unauthorised state changes.
- The server kit — any path that bypasses role enforcement, authentication, or path scoping.
- The conformance harness — any input that escapes scenario sandboxing.
- The interop test control plane — any way to enable it without explicit `--test-control-port` flag.

Out of scope :

- DoS via resource exhaustion when no rate limiting is configured (servers are responsible for adapter rate limits per LSDP/1 § 14.3).
- Issues in optional extras (`fastapi`, `uvicorn`, `httpx`) — please report upstream.
- The example scenes under `examples/` (illustrative, not security-reviewed).

## Production deployment notes

- The interop test control plane MUST never be exposed in production. It is off by default and only activated by the `--test-control-port` CLI flag (or by explicitly mounting `lumencast.interop.control_plane.router`).
- `lumencast.server.StaticTokens` is for development. Use a real `Authenticator` implementation (JWT, OIDC, mTLS) in production.
- Always serve LSDP/1 over `wss://` (TLS) in production. Plaintext `ws://` is allowed only on localhost per LSDP/1 § 14.1.
