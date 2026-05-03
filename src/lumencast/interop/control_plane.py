"""HTTP control plane — the ``/test/*`` endpoints described by CONTROL.md.

The plane is FastAPI-based. Mount it on a separate port from the LSDP/1
WebSocket so production servers can omit the binding entirely.

Importing this module requires ``fastapi`` (the ``[interop]`` extra) ;
the protocol codec stays import-free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:
    from fastapi import APIRouter, Request, Response
    from fastapi.responses import JSONResponse
except ImportError as _e:  # pragma: no cover
    msg = (
        "lumencast.interop.control_plane requires the [interop] extra: "
        'pip install "lumencast[interop]"'
    )
    raise ImportError(msg) from _e

from lumencast.protocol.types import Role
from lumencast.server.auth import Identity, StaticTokens
from lumencast.server.input import parse_inline_specs
from lumencast.server.scene import EmptyPatchesError

if TYPE_CHECKING:
    from lumencast.server.server import Server


_PLACEHOLDER_ROLES: dict[str, Role] = {
    "$TOKEN_OPERATOR": Role.OPERATOR,
    "$TOKEN_VIEWER": Role.VIEWER,
    "$TOKEN_SERVICE": Role.SERVICE,
    "$TOKEN_TEST": Role.TEST,
}


def build_router(server: Server, *, ws_url_hint: str = "") -> APIRouter:
    """Return a FastAPI :class:`APIRouter` exposing the five ``/test/*`` endpoints.

    ``ws_url_hint`` is echoed in the ``/test/setup`` response. Pass the
    canonical ``ws://host:port/lsdp.v1`` URL the harness should dial.
    The CLI ``serve-scenario`` builds this from the bound listener.
    """
    router = APIRouter()

    # The control plane mutates a StaticTokens authenticator. Production-style
    # authenticators stay as-is — the harness can still drive setup, but auth
    # tokens won't be installed for it. The interop CLI wires StaticTokens by
    # default to make this work.
    auth = server.auth if isinstance(server.auth, StaticTokens) else None

    @router.post("/test/setup")
    async def setup(request: Request) -> Response:
        try:
            body: Any = await request.json()
        except Exception as e:
            return _problem(400, "bad-body", f"invalid JSON: {e}")
        if not isinstance(body, dict):
            return _problem(400, "bad-body", "request body must be a JSON object")

        bundles = body.get("bundles") or []
        if not isinstance(bundles, list) or len(bundles) == 0:
            return _problem(400, "missing-bundle", "at least one bundle required")

        await server.reset()
        if auth is not None:
            _install_tokens(auth, body.get("tokens"))

        primary = bundles[0]
        if not isinstance(primary, dict):
            return _problem(400, "bad-bundle", "bundle must be a JSON object")
        bundle_id = str(primary.get("id", ""))
        bundle_hash = str(primary.get("hash") or "")
        inline = primary.get("inline") if isinstance(primary.get("inline"), dict) else {}
        # `inline.scene_id` overrides `bundle.id` per CONTROL.md.
        effective_id = bundle_id
        sid = inline.get("scene_id") if isinstance(inline, dict) else None
        if isinstance(sid, str) and sid:
            effective_id = sid

        kwargs: dict[str, Any] = {}
        if bundle_hash:
            kwargs["scene_version"] = bundle_hash
        if isinstance(inline, dict) and inline.get("operator_inputs"):
            specs = parse_inline_specs(inline["operator_inputs"])
            if specs:
                kwargs["operator_inputs"] = specs
        scene = server.new_scene(effective_id, **kwargs)

        # initial_state takes precedence over inline.defaults.
        state = body.get("initial_state")
        if not isinstance(state, dict) or not state:
            defaults = inline.get("defaults") if isinstance(inline, dict) else None
            if isinstance(defaults, dict) and defaults:
                state = defaults
        if isinstance(state, dict) and state:
            try:
                await scene.set(state)
            except (EmptyPatchesError, ValueError) as e:
                return _problem(400, "bad-initial-state", str(e))

        await server.set_active(effective_id)

        # Register secondary bundles for the multi-bundle scenarios.
        for sec in bundles[1:]:
            if not isinstance(sec, dict):
                continue
            sec_id = str(sec.get("id", ""))
            sec_inline = sec.get("inline") if isinstance(sec.get("inline"), dict) else {}
            sec_sid = sec_inline.get("scene_id") if isinstance(sec_inline, dict) else None
            if isinstance(sec_sid, str) and sec_sid:
                sec_id = sec_sid
            sec_hash = str(sec.get("hash") or "")
            kwargs2: dict[str, Any] = {}
            if sec_hash:
                kwargs2["scene_version"] = sec_hash
            server.new_scene(sec_id, **kwargs2)

        return JSONResponse(
            content={
                "ws_url": ws_url_hint,
                "scene_id": effective_id,
                "scene_version": bundle_hash,
            }
        )

    @router.post("/test/reset")
    async def reset() -> Response:
        await server.reset()
        if auth is not None:
            auth.reset()
        return Response(status_code=204)

    @router.get("/test/state")
    async def state() -> Response:
        scene = server.active_scene()
        if scene is None:
            return _problem(409, "no-active-scene", "/test/setup not called since last /test/reset")
        s = await scene.state()
        return JSONResponse(
            content={
                "scene_id": scene.id,
                "scene_version": scene.version,
                "state": s,
            }
        )

    @router.post("/test/emit")
    async def emit(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception as e:
            return _problem(400, "bad-body", f"invalid JSON: {e}")
        if not isinstance(body, dict):
            return _problem(400, "bad-body", "request body must be a JSON object")
        patches_raw = body.get("patches")
        if not isinstance(patches_raw, list) or not patches_raw:
            return _problem(400, "empty-patches", "at least one patch required")
        patches: dict[str, Any] = {}
        for p in patches_raw:
            if not isinstance(p, dict) or "path" not in p:
                return _problem(400, "bad-patch", "each patch needs a 'path'")
            patches[str(p["path"])] = p.get("value")
        scene = server.active_scene()
        if scene is None:
            return _problem(409, "no-active-scene", "/test/setup not called")
        try:
            await scene.emit(patches)
        except EmptyPatchesError:
            return _problem(400, "empty-patches", "no patches applied")
        except ValueError as e:
            return _problem(400, "INVALID_VALUE", str(e))
        return Response(status_code=204)

    @router.get("/test/health")
    async def health() -> Response:
        return JSONResponse(
            content={
                "status": "ok",
                "control_plane_version": 1,
                "server": "lumencast-py",
            }
        )

    return router


def _install_tokens(auth: StaticTokens, raw: Any) -> None:
    """Replace the StaticTokens contents with one entry per recognised placeholder.

    ``$TOKEN_INVALID`` is intentionally never installed (per spec).
    Robustness clause : ``null`` / ``[]`` / ``{}`` for ``tokens`` MUST
    be accepted ; cross-language harnesses serialise empty as ``null``
    in some languages.
    """
    auth.reset()
    if not isinstance(raw, dict):
        return
    for placeholder, value in raw.items():
        if placeholder == "$TOKEN_INVALID":
            continue
        if not isinstance(value, str) or not value:
            continue
        role = _PLACEHOLDER_ROLES.get(placeholder)
        if role is None:
            continue
        auth.set(value, Identity(subject=placeholder, role=role))


def _problem(status: int, code: str, detail: str) -> Response:
    """Return an RFC 7807 ``application/problem+json`` response."""
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": f"control: {code}",
            "status": status,
            "detail": detail,
        },
    )
