"""Per-scene leaf-grain state map.

Internal implementation detail of :class:`Scene` ; the public surface is
``Scene.set`` and ``Scene.emit``.
"""

from __future__ import annotations

import asyncio
from typing import Any


class Store:
    """Asynchronous leaf-grain state store.

    Keys are dotted leaf paths ; values are arbitrary JSON-compatible
    Python objects. The store is async-safe via a single internal lock,
    matching the FastAPI / uvicorn co-operative concurrency model.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._state: dict[str, Any] = {}

    async def snapshot(self) -> dict[str, Any]:
        """Return a defensive copy of the current state."""
        async with self._lock:
            return dict(self._state)

    async def apply(self, patches: dict[str, Any]) -> list[tuple[str, Any]]:
        """Mutate the store and return ``(path, value)`` patch records.

        Empty patch maps raise :class:`ValueError`. The returned list
        preserves the iteration order of ``patches`` so the caller can
        ship a deterministic ``Delta`` frame.
        """
        if not patches:
            msg = "store: empty patches"
            raise ValueError(msg)
        out: list[tuple[str, Any]] = []
        async with self._lock:
            for path, value in patches.items():
                self._state[path] = value
                out.append((path, value))
        return out

    async def reset(self) -> None:
        """Drop every entry."""
        async with self._lock:
            self._state.clear()
