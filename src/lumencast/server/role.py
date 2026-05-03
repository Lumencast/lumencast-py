"""Role / write-authority predicates shared by server and interop layers."""

from __future__ import annotations

from collections.abc import Sequence

from lumencast.protocol.leaf_path import has_prefix
from lumencast.protocol.types import Role


def role_can_write(role: Role, path: str, *, paths: Sequence[str] | None = None) -> bool:
    """Return True if a connection of ``role`` may write ``path``.

    - ``OPERATOR`` : any path under ``__inputs.*``.
    - ``SERVICE`` : ``__inputs.*`` further restricted by ``paths`` (an
      optional service-token claim). Empty/None ``paths`` means no extra
      restriction.
    - ``TEST`` : ``__test.*`` only.
    - ``VIEWER`` and any other value : never writes.
    """
    if role is Role.OPERATOR:
        return has_prefix(path, "__inputs")
    if role is Role.SERVICE:
        if not has_prefix(path, "__inputs"):
            return False
        if not paths:
            return True
        return any(_pattern_matches(p, path) for p in paths)
    if role is Role.TEST:
        return has_prefix(path, "__test")
    return False


def _pattern_matches(pattern: str, path: str) -> bool:
    """Compare a service-token path pattern against a concrete path.

    Suffix ``*`` and ``.*`` match any descendant. Bare patterns match
    exact + segment-aware prefix.
    """
    if not pattern:
        return False
    if pattern == path:
        return True
    if pattern.endswith(".*"):
        return has_prefix(path, pattern[:-2])
    if pattern.endswith("*"):
        root = pattern[:-1]
        if root.endswith("."):
            return has_prefix(path, root[:-1])
    return has_prefix(path, pattern)
