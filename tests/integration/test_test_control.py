"""HTTP control-plane endpoint tests.

Boots a Server in-process with the control-plane router mounted, then
hits the five ``/test/*`` endpoints with httpx's ASGI transport.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

httpx = pytest.importorskip("httpx")
pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402

from lumencast.interop.control_plane import build_router  # noqa: E402
from lumencast.server.auth import StaticTokens  # noqa: E402
from lumencast.server.server import Server  # noqa: E402


def _build_app() -> tuple[FastAPI, Server]:
    server = Server(auth=StaticTokens())
    app = FastAPI()
    app.include_router(build_router(server, ws_url_hint="ws://test/lsdp.v1"))
    return app, server


@pytest.mark.asyncio
async def test_health() -> None:
    app, _ = _build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/test/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["control_plane_version"] == 1
        assert body["server"] == "lumencast-py"


@pytest.mark.asyncio
async def test_setup_then_state() -> None:
    app, server = _build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        setup_body = {
            "scenario": "test",
            "tokens": {"$TOKEN_OPERATOR": "tok-op"},
            "bundles": [
                {
                    "id": "scene1",
                    "hash": "sha256:" + "a" * 64,
                    "inline": {
                        "lsml": "1.0",
                        "scene_id": "scene1",
                        "operator_inputs": [
                            {
                                "path": "__inputs.title",
                                "type": "string",
                                "constraints": {"maxLength": 80},
                            },
                        ],
                    },
                }
            ],
            "initial_state": {"__inputs.title": "hello"},
        }
        r1 = await client.post("/test/setup", json=setup_body)
        assert r1.status_code == 200, r1.text
        body = r1.json()
        assert body["scene_id"] == "scene1"
        assert body["ws_url"] == "ws://test/lsdp.v1"

        r2 = await client.get("/test/state")
        assert r2.status_code == 200
        s = r2.json()
        assert s["scene_id"] == "scene1"
        assert s["state"] == {"__inputs.title": "hello"}

    # Token was installed.
    assert isinstance(server.auth, StaticTokens)
    assert "tok-op" in server.auth.snapshot()


@pytest.mark.asyncio
async def test_setup_accepts_null_optionals() -> None:
    """Robustness clause from CONTROL.md — null/empty must be accepted."""
    app, _ = _build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        body = {
            "scenario": "auth-denied",
            "tokens": None,
            "bundles": [{"id": "x", "hash": "sha256:" + "0" * 64, "inline": {"scene_id": "x"}}],
            "initial_state": None,
        }
        r = await client.post("/test/setup", json=body)
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_setup_rejects_missing_bundles() -> None:
    app, _ = _build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post("/test/setup", json={"scenario": "x"})
        assert r.status_code == 400
        assert "bundle" in r.text.lower()


@pytest.mark.asyncio
async def test_token_invalid_never_installed() -> None:
    """Per CONTROL.md, $TOKEN_INVALID is intentionally never installed."""
    app, server = _build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        body = {
            "scenario": "x",
            "tokens": {
                "$TOKEN_OPERATOR": "tok-op",
                "$TOKEN_INVALID": "tok-bad",
            },
            "bundles": [{"id": "x", "hash": "sha256:" + "0" * 64, "inline": {"scene_id": "x"}}],
            "initial_state": {},
        }
        r = await client.post("/test/setup", json=body)
        assert r.status_code == 200
    assert isinstance(server.auth, StaticTokens)
    snap = server.auth.snapshot()
    assert "tok-op" in snap
    assert "tok-bad" not in snap


@pytest.mark.asyncio
async def test_emit_then_state_reflects_delta() -> None:
    app, _ = _build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/test/setup",
            json={
                "scenario": "x",
                "tokens": {},
                "bundles": [{"id": "x", "hash": "sha256:" + "0" * 64, "inline": {"scene_id": "x"}}],
                "initial_state": {"a": 0},
            },
        )
        r = await client.post("/test/emit", json={"patches": [{"path": "a", "value": 7}]})
        assert r.status_code == 204, r.text
        r2 = await client.get("/test/state")
        assert r2.json()["state"]["a"] == 7


@pytest.mark.asyncio
async def test_state_409_when_no_active_scene() -> None:
    app, _ = _build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/test/state")
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_reset_clears_state() -> None:
    app, _ = _build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            "/test/setup",
            json={
                "scenario": "x",
                "bundles": [{"id": "x", "hash": "sha256:" + "0" * 64, "inline": {"scene_id": "x"}}],
                "initial_state": {"a": 0},
            },
        )
        r = await client.post("/test/reset")
        assert r.status_code == 204
        r2 = await client.get("/test/state")
        assert r2.status_code == 409
