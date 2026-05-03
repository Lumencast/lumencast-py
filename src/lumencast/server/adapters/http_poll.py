"""HTTP polling adapter — calls a URL on an interval, writes the response into a scene."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from lumencast.server.scene import Scene

_log = logging.getLogger("lumencast.adapters.http_poll")


async def http_poll_adapter(
    scene: Scene,
    url: str,
    *,
    interval: float = 0.2,
    transform: Callable[[Any], dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> None:
    """Poll ``url`` every ``interval`` seconds and emit the response as a delta.

    Requires the ``[interop]`` extra (``httpx``).
    """
    try:
        import httpx
    except ImportError as e:
        msg = "http_poll_adapter requires httpx (install with [interop] extra)"
        raise ImportError(msg) from e

    async with httpx.AsyncClient(headers=headers, timeout=interval * 4) as client:
        while True:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                body = resp.json()
            except Exception as e:
                _log.warning("poll %s failed: %s", url, e)
                await asyncio.sleep(interval)
                continue
            patches = transform(body) if transform else _flatten(body)
            if patches:
                await scene.emit(patches)
            await asyncio.sleep(interval)


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Default flatten — turns nested dicts into dotted leaf paths."""
    if not isinstance(value, dict):
        return {prefix or "value": value}
    out: dict[str, Any] = {}
    for k, v in value.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


__all__ = ["http_poll_adapter"]


# Touch json so the import isn't reported unused even on partial typecheck runs.
_ = json
