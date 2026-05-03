"""Self-interop test : spawn ``serve-scenario``, drive with ``conformance``.

Asserts 9/9 required scenarios PASS — the same gate JS / RS shipped.
Set ``LUMENCAST_PROTOCOL_REPO`` to the lumencast-protocol checkout so
the conformance CLI can locate the scenarios.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

httpx = pytest.importorskip("httpx")
uvicorn = pytest.importorskip("uvicorn")
websockets = pytest.importorskip("websockets")


REQUIRED_SCENARIOS_EXPECTED = 9


def _resolve_protocol_repo() -> Path | None:
    env = os.environ.get("LUMENCAST_PROTOCOL_REPO")
    if env:
        p = Path(env)
        if (p / "conformance" / "v1" / "scenarios").is_dir():
            return p
    sibling = Path.cwd().parent / "lumencast-protocol"
    if (sibling / "conformance" / "v1" / "scenarios").is_dir():
        return sibling
    return None


@pytest.mark.asyncio
async def test_self_interop_required_scenarios_pass() -> None:
    repo = _resolve_protocol_repo()
    if repo is None:
        pytest.skip("LUMENCAST_PROTOCOL_REPO not set and no sibling lumencast-protocol checkout")

    # Spawn `python -m lumencast serve-scenario` ; let it allocate ports.
    serve_cmd = [
        sys.executable,
        "-m",
        "lumencast",
        "serve-scenario",
        "--ws-port",
        "0",
        "--test-control-port",
        "0",
    ]
    server_proc = await asyncio.create_subprocess_exec(
        *serve_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        # Wait for the discovery JSON line on stdout.
        assert server_proc.stdout is not None
        discovery_line: bytes | None = None
        try:
            discovery_line = await asyncio.wait_for(server_proc.stdout.readline(), timeout=15.0)
        except TimeoutError:
            pytest.fail("serve-scenario did not print discovery line within 15s")
        assert discovery_line, "serve-scenario closed stdout without discovery"
        discovery = json.loads(discovery_line.decode().strip())
        ws_url = discovery["ws_url"]
        control_url = discovery["control_url"]
        assert ws_url.startswith("ws://")
        assert control_url.startswith("http://")

        # Drive the server through the suite.
        env = os.environ.copy()
        env["LUMENCAST_PROTOCOL_REPO"] = str(repo)
        conf_proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "lumencast",
            "conformance",
            "--server",
            ws_url,
            "--control-url",
            control_url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                conf_proc.communicate(),
                timeout=120.0,
            )
        except TimeoutError:
            conf_proc.kill()
            await conf_proc.wait()
            pytest.fail("conformance run did not complete in 120s")
        rc = conf_proc.returncode
        stderr_text = stderr_bytes.decode(errors="replace")
        stdout_text = stdout_bytes.decode(errors="replace")
        report_text = stderr_text + stdout_text

        # Count PASS lines for required scenarios.
        pass_lines = [line for line in report_text.splitlines() if line.startswith("PASS")]
        assert len(pass_lines) >= REQUIRED_SCENARIOS_EXPECTED, (
            f"expected ≥{REQUIRED_SCENARIOS_EXPECTED} PASS, got {len(pass_lines)}\n"
            f"--- conformance output ---\n{report_text}"
        )
        assert rc == 0, f"conformance returned rc={rc}\n{report_text}"
    finally:
        server_proc.terminate()
        try:
            await asyncio.wait_for(server_proc.wait(), timeout=5.0)
        except TimeoutError:
            server_proc.kill()
            await server_proc.wait()
