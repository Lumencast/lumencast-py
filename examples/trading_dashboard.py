"""Trading dashboard example.

Spins up a scene whose state is fed by a periodic adapter coroutine.
Demonstrates the Scene.emit fan-out and how to compose adapters with the
server kit. Mock data (random walk) so the example runs offline.
"""

from __future__ import annotations

import asyncio
import random

from lumencast.protocol.types import Role
from lumencast.server.auth import Identity, StaticTokens
from lumencast.server.scene import Scene
from lumencast.server.server import Server


async def random_walk(scene: Scene, *, interval: float = 0.5) -> None:
    """Push a random-walk price update on every interval."""
    price = 100.0
    while True:
        price += random.uniform(-1, 1)
        await scene.emit(
            {
                "ticker.price": round(price, 2),
                "ticker.last_update_ts": asyncio.get_event_loop().time(),
            }
        )
        await asyncio.sleep(interval)


async def main() -> None:
    auth = StaticTokens({"tok-vw": Identity(subject="viewer", role=Role.VIEWER)})
    server = Server(auth=auth)
    scene = server.new_scene("trading")
    await scene.set({"ticker.symbol": "DEMO", "ticker.price": 100.0})
    await server.set_active("trading")

    asyncio.create_task(random_walk(scene))

    print("listening on ws://127.0.0.1:8080/lsdp.v1 (token: tok-vw)")
    await server.run(host="127.0.0.1", port=8080)


if __name__ == "__main__":
    asyncio.run(main())
