"""Authentication primitives for the LSDP/1 server kit.

The kit ships :class:`StaticTokens` for development. Production callers
implement the :class:`Authenticator` protocol against a JWT verifier,
mTLS-derived principal, or a remote token-introspection endpoint.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from lumencast.protocol.types import Role
from lumencast.server.role import role_can_write


class AuthError(Exception):
    """Canonical authentication failure.

    Authenticators raise this when a token is invalid, expired, or
    revoked. The server kit translates it into an ``AUTH_DENIED`` error
    frame followed by a close.
    """


@dataclass(slots=True)
class Identity:
    """Principal returned by an Authenticator after a successful validation.

    ``role`` drives the authorisation matrix ; ``paths`` optionally
    restricts a service token to a subset of ``__inputs.*``.
    """

    subject: str = ""
    role: Role | None = None
    paths: Sequence[str] = field(default_factory=tuple)

    def is_authenticated(self) -> bool:
        """Return True when the identity carries a valid role."""
        return self.role is not None

    def can_write(self, path: str) -> bool:
        """Apply the role / scope gate for ``path``."""
        if self.role is None:
            return False
        return role_can_write(self.role, path, paths=self.paths)


def Anonymous() -> Identity:
    """Return an unauthenticated :class:`Identity`."""
    return Identity()


@runtime_checkable
class Authenticator(Protocol):
    """Validate a token and yield an :class:`Identity`.

    Implementations MUST raise :class:`AuthError` on invalid tokens.
    Returning an Identity with ``role is None`` is also treated as
    failure by the server kit (defensive).
    """

    async def authenticate(self, token: str) -> Identity:
        """Validate ``token`` and return the resolved identity."""
        ...


class StaticTokens:
    """Development-only :class:`Authenticator` backed by a fixed map.

    Thread-safe. The interop control plane mutates this between scenarios
    via :meth:`set` / :meth:`reset`. Do not deploy to production —
    ``lumencast init`` (when added) will flag this with a TODO.
    """

    def __init__(self, tokens: dict[str, Identity] | None = None) -> None:
        self._lock = threading.RLock()
        self._tokens: dict[str, Identity] = dict(tokens or {})

    async def authenticate(self, token: str) -> Identity:
        with self._lock:
            id_ = self._tokens.get(token)
        if id_ is None:
            raise AuthError("auth: token invalid, expired, or revoked")
        return id_

    def set(self, token: str, identity: Identity) -> None:
        """Add or replace a token mapping."""
        with self._lock:
            self._tokens[token] = identity

    def delete(self, token: str) -> None:
        """Remove a token mapping. Idempotent."""
        with self._lock:
            self._tokens.pop(token, None)

    def reset(self) -> None:
        """Drop every token mapping."""
        with self._lock:
            self._tokens.clear()

    def snapshot(self) -> dict[str, Identity]:
        """Return a defensive copy of the current map (testing helper)."""
        with self._lock:
            return dict(self._tokens)
