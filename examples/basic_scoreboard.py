"""Basic scoreboard example — mirrors the Go / JS / Rust counterparts.

Run with :

    pip install "lumencast[server]"
    python examples/basic_scoreboard.py

Then connect a runtime to ws://127.0.0.1:8080/lsdp.v1 with the operator
token "tok-op". Inputs to ``__inputs.show_title`` echo back as deltas to
every subscriber.
"""

from __future__ import annotations

import asyncio

from lumencast.protocol.types import Role
from lumencast.server.auth import Identity, StaticTokens
from lumencast.server.input import InputSpec
from lumencast.server.server import Server


async def main() -> None:
    auth = StaticTokens(
        {
            "tok-op": Identity(subject="alice", role=Role.OPERATOR),
            "tok-vw": Identity(subject="bob", role=Role.VIEWER),
        }
    )
    server = Server(auth=auth)

    scene = server.new_scene(
        "scoreboard",
        operator_inputs=[
            InputSpec(path="__inputs.show_title", type="string", max_length=80),
            InputSpec(path="__inputs.score_home", type="number", min_value=0, max_value=999),
            InputSpec(path="__inputs.score_away", type="number", min_value=0, max_value=999),
        ],
    )
    await scene.set(
        {
            "__inputs.show_title": "Match Day",
            "__inputs.score_home": 0,
            "__inputs.score_away": 0,
        }
    )
    await server.set_active("scoreboard")

    print("listening on ws://127.0.0.1:8080/lsdp.v1 — Ctrl-C to stop")
    await server.run(host="127.0.0.1", port=8080)


if __name__ == "__main__":
    asyncio.run(main())
