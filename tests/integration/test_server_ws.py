"""End-to-end WebSocket tests against an in-process Server.

Uses ``websockets`` to dial a uvicorn-served LSDP/1 endpoint on an
ephemeral port. Validates the subscribe → snapshot path and the
operator input echo.
"""

from __future__ import annotations

import asyncio
import json
import socket
from collections.abc import AsyncGenerator

import pytest

pytestmark = pytest.mark.integration

uvicorn = pytest.importorskip("uvicorn")
websockets = pytest.importorskip("websockets")

from lumencast.protocol.envelope import SUBPROTOCOL  # noqa: E402
from lumencast.protocol.types import Role  # noqa: E402
from lumencast.server.auth import Identity, StaticTokens  # noqa: E402
from lumencast.server.input import InputSpec  # noqa: E402
from lumencast.server.server import Server  # noqa: E402


def _free_port() -> int:
    s = socket.socket()
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


@pytest.fixture
async def running_server() -> AsyncGenerator[tuple[Server, int]]:
    """Boot a server on an ephemeral port, yield (server, port)."""
    port = _free_port()
    auth = StaticTokens(
        {
            "tok-op": Identity(subject="alice", role=Role.OPERATOR),
            "tok-vw": Identity(subject="bob", role=Role.VIEWER),
        }
    )
    server = Server(auth=auth)
    scene = server.new_scene(
        "main",
        operator_inputs=[InputSpec(path="__inputs.title", type="string", max_length=80)],
    )
    await scene.set({"__inputs.title": "hello"})
    await server.set_active("main")

    config = uvicorn.Config(server.app(), host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    task = asyncio.create_task(srv.serve())
    for _ in range(200):
        if srv.started:
            break
        await asyncio.sleep(0.01)
    assert srv.started, "server failed to start"
    try:
        yield server, port
    finally:
        srv.should_exit = True
        srv.force_exit = True
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except (TimeoutError, asyncio.CancelledError):
            task.cancel()
            try:
                await task
            except (TimeoutError, asyncio.CancelledError, Exception):
                pass


@pytest.mark.asyncio
async def test_subscribe_returns_snapshot(running_server: tuple[Server, int]) -> None:
    _, port = running_server
    url = f"ws://127.0.0.1:{port}/lsdp.v1"
    async with websockets.connect(url, subprotocols=[SUBPROTOCOL]) as ws:
        await ws.send(json.dumps({"v": 1, "type": "subscribe", "token": "tok-op"}))
        raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
    frame = json.loads(raw)
    assert frame["type"] == "snapshot"
    assert frame["seq"] == 1
    assert frame["state"] == {"__inputs.title": "hello"}


@pytest.mark.asyncio
async def test_invalid_token_rejected(running_server: tuple[Server, int]) -> None:
    _, port = running_server
    url = f"ws://127.0.0.1:{port}/lsdp.v1"
    async with websockets.connect(url, subprotocols=[SUBPROTOCOL]) as ws:
        await ws.send(json.dumps({"v": 1, "type": "subscribe", "token": "ghost"}))
        # Server emits an error frame then closes.
        raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
        frame = json.loads(raw)
        assert frame["type"] == "error"
        assert frame["code"] == "AUTH_DENIED"


@pytest.mark.asyncio
async def test_operator_input_echoed_as_delta(running_server: tuple[Server, int]) -> None:
    _, port = running_server
    url = f"ws://127.0.0.1:{port}/lsdp.v1"
    async with websockets.connect(url, subprotocols=[SUBPROTOCOL]) as ws:
        await ws.send(json.dumps({"v": 1, "type": "subscribe", "token": "tok-op"}))
        snap = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert snap["type"] == "snapshot"
        await ws.send(
            json.dumps(
                {
                    "v": 1,
                    "type": "input",
                    "patches": [{"path": "__inputs.title", "value": "world"}],
                }
            )
        )
        delta = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert delta["type"] == "delta"
        assert delta["seq"] == 2
        assert delta["patches"] == [{"path": "__inputs.title", "value": "world"}]


@pytest.mark.asyncio
async def test_viewer_cannot_input(running_server: tuple[Server, int]) -> None:
    _, port = running_server
    url = f"ws://127.0.0.1:{port}/lsdp.v1"
    async with websockets.connect(url, subprotocols=[SUBPROTOCOL]) as ws:
        await ws.send(json.dumps({"v": 1, "type": "subscribe", "token": "tok-vw"}))
        await asyncio.wait_for(ws.recv(), timeout=2.0)  # snapshot
        await ws.send(
            json.dumps(
                {
                    "v": 1,
                    "type": "input",
                    "patches": [{"path": "__inputs.title", "value": "boom"}],
                }
            )
        )
        err = json.loads(await asyncio.wait_for(ws.recv(), timeout=2.0))
        assert err["type"] == "error"
        assert err["code"] == "WRITE_FORBIDDEN"
