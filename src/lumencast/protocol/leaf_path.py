"""LSDP/1 leaf path validation and scope substitution.

A *leaf path* is a dotted reference to a single leaf in the subscription
state map (``show.title``, ``players.0.name``, ``__inputs.locale``).
"""

from __future__ import annotations

from typing import Final

LeafPath = str
"""Type alias — leaf paths are plain strings on the wire."""

RESERVED_NAMESPACES: Final[tuple[str, ...]] = (
    "__inputs",
    "__system",
    "__test",
    "__schema",
)


def validate_path(path: str, *, allow_template: bool = False) -> None:
    """Validate ``path`` as a wire-level leaf path.

    Segments are alphanumeric + underscore. Numeric indices (``players.0``)
    are accepted. Hyphens, spaces, and other punctuation are forbidden.
    When ``allow_template`` is True, ``{name}`` placeholders inside
    segments are accepted (used by the LSML editor for repeat templates ;
    forbidden on the wire).

    Raises :class:`ValueError` on any malformed segment.
    """
    if not path:
        msg = "leaf path: empty"
        raise ValueError(msg)
    segments = path.split(".")
    for i, seg in enumerate(segments):
        if not seg:
            msg = f"leaf path: empty segment at {i}"
            raise ValueError(msg)
        if allow_template and seg.startswith("{") and seg.endswith("}"):
            inner = seg[1:-1]
            if not inner:
                msg = f"leaf path: empty scope at {i}"
                raise ValueError(msg)
            if not _is_identifier(inner):
                msg = f"leaf path: invalid scope {inner!r}"
                raise ValueError(msg)
            continue
        if not _valid_segment(seg):
            msg = f"leaf path: invalid segment {seg!r} at {i}"
            raise ValueError(msg)


def is_reserved(path: str) -> bool:
    """Return True if ``path`` falls under a reserved namespace."""
    for ns in RESERVED_NAMESPACES:
        if path == ns or path.startswith(ns + "."):
            return True
    return False


def namespace(path: str) -> str:
    """Return the leading segment of ``path`` (or the whole path if no dot)."""
    idx = path.find(".")
    if idx < 0:
        return path
    return path[:idx]


def has_prefix(path: str, prefix: str) -> bool:
    """Segment-aware prefix match : ``players`` matches ``players.0`` but
    not ``playerstats.0``.
    """
    if path == prefix:
        return True
    return path.startswith(prefix + ".")


def substitute(path: str, scope: dict[str, str]) -> str:
    """Replace every ``{name}`` placeholder in ``path`` with ``scope[name]``.

    Validates the result is a wire-level leaf path. Raises :class:`ValueError`
    on unknown placeholders, unterminated braces, or invalid resulting paths.
    """
    if "{" not in path:
        validate_path(path)
        return path
    out: list[str] = []
    i = 0
    while i < len(path):
        ch = path[i]
        if ch != "{":
            out.append(ch)
            i += 1
            continue
        end = path.find("}", i + 1)
        if end < 0:
            msg = f"leaf path: unterminated scope placeholder at {i}"
            raise ValueError(msg)
        name = path[i + 1 : end]
        if name not in scope:
            msg = f"leaf path: unknown scope {name!r}"
            raise ValueError(msg)
        out.append(scope[name])
        i = end + 1
    result = "".join(out)
    validate_path(result)
    return result


def _valid_segment(seg: str) -> bool:
    """Letters, digits, underscores. First char may be a digit (numeric index)."""
    for ch in seg:
        if ch.isalpha() or ch == "_" or ch.isdigit():
            continue
        return False
    return True


def _is_identifier(s: str) -> bool:
    """Stricter — letters/digits/underscores, MUST start with letter or underscore."""
    if not s:
        return False
    for i, ch in enumerate(s):
        if ch.isalpha() or ch == "_":
            continue
        if ch.isdigit() and i > 0:
            continue
        return False
    return True
