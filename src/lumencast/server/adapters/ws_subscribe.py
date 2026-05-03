"""WebSocket subscribe adapter — relays an upstream WS into a scene."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from lumencast.server.scene import Scene

_log = logging.getLogger("lumencast.adapters.ws_subscribe")


async def ws_subscribe_adapter(
    scene: Scene,
    url: str,
    *,
    transform: Callable[[Any], dict[str, Any]] | None = None,
    reconnect_delay: float = 1.0,
) -> None:
    """Maintain an upstream WebSocket and emit each message as a scene delta.

    Reconnects with a flat back-off on disconnects. Requires the
    ``[server]`` extra (``websockets``).
    """
    try:
        import websockets.asyncio.client as websockets
    except ImportError as e:
        msg = "ws_subscribe_adapter requires websockets (install with [server] extra)"
        raise ImportError(msg) from e

    while True:
        try:
            async with websockets.connect(url) as ws:
                async for raw in ws:
                    try:
                        body = json.loads(raw)
                    except ValueError:
                        _log.warning("upstream %s: non-JSON frame, dropping", url)
                        continue
                    patches = (
                        transform(body) if transform else (body if isinstance(body, dict) else {})
                    )
                    if patches:
                        await scene.emit(patches)
        except Exception as e:
            _log.warning("ws %s closed: %s — reconnecting", url, e)
            await asyncio.sleep(reconnect_delay)


__all__ = ["ws_subscribe_adapter"]
