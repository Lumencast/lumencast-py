"""Cross-language interop hooks for LSDP/1 servers.

Two surfaces :

- :mod:`lumencast.interop.control_plane` exposes the HTTP ``/test/*``
  endpoints described by ``lumencast-protocol/interop/CONTROL.md``.
- :mod:`lumencast.interop.http_driver` is the harness-side counterpart —
  drives any LSDP/1 server that exposes the control plane.

The control plane MUST never be exposed in production. It is off by
default and only mounted when explicitly requested (``--test-control-port``
on the CLI or ``Server.app(control_plane=True)``).
"""

from __future__ import annotations

from lumencast.interop.control_plane import build_router
from lumencast.interop.http_driver import HTTPDriver, canonical_interop_tokens

__all__ = ["HTTPDriver", "build_router", "canonical_interop_tokens"]
