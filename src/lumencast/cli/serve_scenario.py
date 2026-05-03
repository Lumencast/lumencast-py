"""``lumencast serve-scenario`` — boot WS + control plane on two ports.

On startup, prints exactly one JSON line on stdout :

    {"control_url":"http://...","ws_url":"ws://.../lsdp.v1"}

Then becomes silent. The interop driver waits for that line before
running its harness.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import socket
import sys
from collections.abc import Sequence
from typing import Any

# FastAPI / uvicorn imports MUST live at module level — PEP 563 string
# annotations are resolved by FastAPI via ``get_type_hints`` against the
# function's ``__globals__``, which is the module dict. Importing them
# inside ``run()`` would make ``WebSocket`` unresolvable and FastAPI would
# treat the parameter as a query field, returning HTTP 403 on every WS
# upgrade.
try:
    import uvicorn
    from fastapi import FastAPI, WebSocket
except ImportError as _e:  # pragma: no cover
    msg = 'lumencast serve-scenario requires the [server] extra: pip install "lumencast[server]"'
    raise ImportError(msg) from _e

from lumencast.interop.control_plane import build_router
from lumencast.server.auth import StaticTokens
from lumencast.server.server import Server
from lumencast.server.ws_handler import handle_ws


async def run(argv: Sequence[str]) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="lumencast serve-scenario")
    parser.add_argument("--ws-port", type=int, default=0, help="LSDP/1 WS port (0 = OS-assigned)")
    parser.add_argument(
        "--test-control-port",
        type=int,
        default=0,
        help="HTTP control plane port (0 = OS-assigned)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    args = parser.parse_args(argv)

    # Bind both ports up-front so the discovery line carries the resolved
    # addresses even when 0 was requested.
    ws_port = _bind_port(args.host, args.ws_port)
    control_port = _bind_port(args.host, args.test_control_port)

    ws_url = f"ws://{args.host}:{ws_port}/lsdp.v1"
    control_url = f"http://{args.host}:{control_port}"

    auth = StaticTokens()
    server = Server(auth=auth)

    ws_app = FastAPI()

    @ws_app.websocket("/lsdp.v1")
    async def lsdp_endpoint(ws: WebSocket) -> None:
        await handle_ws(server, ws)

    control_app = FastAPI()
    control_app.include_router(build_router(server, ws_url_hint=ws_url))

    ws_config = uvicorn.Config(ws_app, host=args.host, port=ws_port, log_level="warning")
    control_config = uvicorn.Config(
        control_app, host=args.host, port=control_port, log_level="warning"
    )
    ws_server = uvicorn.Server(ws_config)
    control_server = uvicorn.Server(control_config)

    # Print the discovery line *after* uvicorn binds (we don't want the
    # parent driver to dial before we're ready). Race-free strategy : bind
    # both servers in parallel, wait for them to report .started=True, then
    # emit the line.
    ws_task = asyncio.create_task(ws_server.serve())
    control_task = asyncio.create_task(control_server.serve())

    await _wait_for_started(ws_server)
    await _wait_for_started(control_server)

    print(
        json.dumps({"control_url": control_url, "ws_url": ws_url}, separators=(",", ":")),
        flush=True,
    )

    # Wait for either server to exit (clean shutdown or signal).
    done, pending = await asyncio.wait(
        {ws_task, control_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    for task in done:
        exc = task.exception()
        if exc is not None and not isinstance(exc, asyncio.CancelledError):
            print(f"serve-scenario: {exc}", file=sys.stderr)
            return 1
    return 0


def _bind_port(host: str, requested: int) -> int:
    """Resolve ``requested`` (0 = ephemeral) to a concrete port.

    Picks via a transient socket bind so uvicorn can rebind cleanly. There
    is a vanishingly small race here ; the interop matrix mitigates by
    retrying scenarios that hit a port conflict.
    """
    if requested != 0:
        return requested
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


async def _wait_for_started(server: Any) -> None:
    """Poll ``server.started`` (uvicorn flag) every 10 ms up to 5 s."""
    for _ in range(500):
        if getattr(server, "started", False):
            return
        await asyncio.sleep(0.01)
