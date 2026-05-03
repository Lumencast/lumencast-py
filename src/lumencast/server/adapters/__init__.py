"""Server-side adapter helpers (HTTP poll, WS subscribe).

Adapters are small async coroutines that pump external data into a
:class:`Scene` via ``scene.emit`` / ``scene.set``. The kit ships
two reference adapters as templates ; production deployments compose
their own.
"""

from __future__ import annotations

from lumencast.server.adapters.http_poll import http_poll_adapter
from lumencast.server.adapters.ws_subscribe import ws_subscribe_adapter

__all__ = ["http_poll_adapter", "ws_subscribe_adapter"]
