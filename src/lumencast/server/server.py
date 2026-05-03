"""Lumencast server kit — public façade.

Wires together :class:`Scene`, :class:`Authenticator`, and the
WebSocket handler into a runnable FastAPI application.

Importing this module requires the ``[server]`` extra (FastAPI +
uvicorn + websockets). The protocol codec stays import-free.
"""

from __future__ import annotations

import asyncio
import logging

try:
    from fastapi import FastAPI, WebSocket
except ImportError as _e:  # pragma: no cover
    msg = 'lumencast.server requires the [server] extra: pip install "lumencast[server]"'
    raise ImportError(msg) from _e

from lumencast.protocol.errors import ErrorCode
from lumencast.protocol.frames import Subscribe
from lumencast.protocol.types import Role
from lumencast.server.auth import Authenticator, Identity
from lumencast.server.input import InputSpec
from lumencast.server.scene import DEFAULT_SCENE_VERSION, Scene, Subscription

_log = logging.getLogger("lumencast.server")


class Server:
    """LSDP/1 server kit.

    Owns a set of :class:`Scene` instances and a WebSocket handler. Use
    :meth:`new_scene` + :meth:`set_active` to register and switch
    scenes ; :meth:`run` boots a uvicorn instance.

    The kit is opinionated about the wire format (LSDP/1 verbatim) and
    unopinionated about everything else. Pass an :class:`Authenticator`
    implementation ; the kit calls it on every WebSocket subscribe.
    """

    def __init__(self, *, auth: Authenticator) -> None:
        self.auth = auth
        self._scenes: dict[str, Scene] = {}
        self._active: str = ""
        self._lock = asyncio.Lock()

    # --- scene management -------------------------------------------------

    def new_scene(
        self,
        scene_id: str,
        *,
        scene_version: str = DEFAULT_SCENE_VERSION,
        operator_inputs: list[InputSpec] | None = None,
    ) -> Scene:
        """Register a new :class:`Scene` under ``scene_id``.

        Reusing an id replaces the previous Scene atomically. The first
        scene registered becomes the active one by default.
        """
        scene = Scene(
            scene_id,
            scene_version=scene_version,
            operator_inputs=operator_inputs,
        )
        prev = self._scenes.get(scene_id)
        self._scenes[scene_id] = scene
        if not self._active:
            self._active = scene_id
        if prev is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(prev.reset())
            except RuntimeError:
                # No running loop — caller is in sync setup, the previous
                # scene's subscribers will be GC'd along with the scene.
                pass
        return scene

    def scene(self, scene_id: str) -> Scene | None:
        """Return the registered scene by id, or ``None``."""
        return self._scenes.get(scene_id)

    def active_scene(self) -> Scene | None:
        """Return the live scene, or ``None`` if none is registered."""
        if not self._active:
            return None
        return self._scenes.get(self._active)

    async def set_active(self, scene_id: str) -> None:
        """Change which scene the live endpoint serves.

        Live subscribers attached to the previous active scene receive a
        ``SceneChanged`` frame followed by a fresh ``Snapshot`` at
        ``seq=1`` on the new scene. Idempotent.
        """
        if scene_id not in self._scenes:
            msg = f"server: scene {scene_id!r} not registered"
            raise KeyError(msg)
        if self._active == scene_id:
            return
        prev_id = self._active
        self._active = scene_id
        prev = self._scenes.get(prev_id) if prev_id else None
        next_scene = self._scenes[scene_id]
        if prev is not None and prev is not next_scene:
            await next_scene.migrate_subscribers_from(prev)

    async def reset(self) -> None:
        """Drop every registered scene and clear active state.

        Test-harness use only — interop control plane calls this between
        scenarios.
        """
        async with self._lock:
            scenes = list(self._scenes.values())
            self._scenes.clear()
            self._active = ""
        for sc in scenes:
            await sc.reset()

    async def detach(self, sub: Subscription) -> None:
        """Remove ``sub`` from whichever scene currently owns it."""
        for sc in list(self._scenes.values()):
            await sc.unsubscribe(sub)

    # --- LSDP routing -----------------------------------------------------

    def resolve_scene(
        self,
        subscribe: Subscribe,
        identity: Identity,
    ) -> tuple[Scene | None, ErrorCode | None, str]:
        """Pick the right Scene for a Subscribe frame.

        Live mode (no ``scene`` field) returns the active scene. Test
        mode demands ``(scene, session)`` and the role MUST be ``test``
        or ``operator``.
        """
        if not subscribe.scene:
            sc = self.active_scene()
            if sc is None:
                return (None, ErrorCode.SCENE_NOT_FOUND, "no active scene")
            return (sc, None, "")
        if identity.role not in {Role.TEST, Role.OPERATOR}:
            return (None, ErrorCode.AUTH_DENIED, "test mode requires test or operator role")
        if not subscribe.session:
            return (None, ErrorCode.SCENE_NOT_FOUND, "test mode requires session")
        sc = self._scenes.get(subscribe.scene)
        if sc is None:
            return (None, ErrorCode.SCENE_NOT_FOUND, "scene not registered")
        return (sc, None, "")

    # --- HTTP / WS surface ------------------------------------------------

    def app(self, *, control_plane: bool = False) -> FastAPI:
        """Return a configured :class:`fastapi.FastAPI` for this server.

        ``control_plane=True`` mounts the interop ``/test/*`` endpoints
        under the same app ; production callers leave this off.
        """
        from lumencast.server.ws_handler import handle_ws

        api = FastAPI(title="lumencast-py", version="0.1.0")

        @api.get("/healthz")
        async def healthz() -> dict[str, str]:
            return {"status": "ok"}

        @api.websocket("/lsdp.v1")
        async def lsdp_endpoint(ws: WebSocket) -> None:
            await handle_ws(self, ws)

        if control_plane:
            from lumencast.interop.control_plane import build_router

            api.include_router(build_router(self))

        return api

    async def run(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 8080,
        control_plane: bool = False,
    ) -> None:
        """Boot a uvicorn server until cancellation.

        Convenience wrapper for the common case ; production deployments
        usually wire :meth:`app` into their existing ASGI stack.
        """
        try:
            import uvicorn
        except ImportError as e:
            msg = (
                'lumencast.server.run requires the [server] extra: pip install "lumencast[server]"'
            )
            raise ImportError(msg) from e

        config = uvicorn.Config(
            self.app(control_plane=control_plane),
            host=host,
            port=port,
            log_level="warning",
        )
        srv = uvicorn.Server(config)
        await srv.serve()


__all__ = ["Server"]
