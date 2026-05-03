"""Server-side abstraction of a Lumencast scene.

A :class:`Scene` owns an id, a current state, and a fan-out of
subscribers. Adapter coroutines call :meth:`set` to seed and
:meth:`emit` to push live deltas. Each subscription owns an
``asyncio.Queue`` ; back-pressured subscribers get a fresh snapshot
instead of an unbounded delta queue.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from lumencast.protocol.frames import Delta, Patch, SceneChanged, Snapshot
from lumencast.protocol.leaf_path import has_prefix
from lumencast.protocol.sequence import SequenceTracker
from lumencast.protocol.types import Role
from lumencast.server.auth import Identity
from lumencast.server.input import InputSpec, check_constraint

DEFAULT_SCENE_VERSION = "sha256:0000000000000000000000000000000000000000000000000000000000000000"


class EmptyPatchesError(ValueError):
    """Raised by :meth:`Scene.set` / :meth:`Scene.emit` on an empty map."""


@dataclass(slots=True, eq=False)
class Subscription:
    """One subscriber's per-WS pipe.

    ``eq=False`` keeps the default ``id()``-based hash so the kit can use
    a :class:`set` to track subscribers without instances accidentally
    comparing equal on field values.
    """

    queue: asyncio.Queue[Any] = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    seq: SequenceTracker = field(default_factory=SequenceTracker)
    live: bool = False
    closed: bool = False
    stale: bool = False

    def close(self) -> None:
        """Mark the subscription closed and unblock any waiting reader."""
        if self.closed:
            return
        self.closed = True
        # Push a sentinel None to wake the writer loop.
        try:
            self.queue.put_nowait(None)
        except asyncio.QueueFull:
            # Drop oldest, retry once.
            try:
                self.queue.get_nowait()
                self.queue.put_nowait(None)
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                pass


class Scene:
    """Server-side scene : state + fan-out.

    Scene is async-safe ; mutating methods coordinate via an internal
    lock. The ``declared_inputs`` map enforces operator_input declaredness
    when non-empty (per LSML 1.0 § 8).
    """

    def __init__(
        self,
        scene_id: str,
        *,
        scene_version: str = DEFAULT_SCENE_VERSION,
        operator_inputs: list[InputSpec] | None = None,
    ) -> None:
        self._id = scene_id
        self._version = scene_version
        from lumencast.server.store import Store  # local import — tighter cycle

        self._store = Store()
        self._lock = asyncio.Lock()
        self._subscribers: set[Subscription] = set()
        self._declared_inputs: dict[str, InputSpec] = {}
        if operator_inputs:
            for spec in operator_inputs:
                self._declared_inputs[spec.path] = spec

    @property
    def id(self) -> str:
        """Scene identifier (operator-chosen)."""
        return self._id

    @property
    def version(self) -> str:
        """Current ``scene_version`` (LSML content hash)."""
        return self._version

    def set_version(self, version: str) -> None:
        """Override the ``scene_version`` field. Call before subscribers attach."""
        self._version = version

    def declare_inputs(self, specs: list[InputSpec]) -> None:
        """Replace the declared input set."""
        self._declared_inputs = {s.path: s for s in specs}

    async def state(self) -> dict[str, Any]:
        """Return a defensive copy of the current authoritative state."""
        return await self._store.snapshot()

    async def set(self, patches: dict[str, Any]) -> None:
        """Seed initial state. Existing subscribers receive a fresh snapshot."""
        if not patches:
            raise EmptyPatchesError("scene: empty patches")
        await self._store.apply(patches)
        await self._refresh_all()

    async def emit(self, patches: dict[str, Any]) -> None:
        """Apply a delta + fan it out to every subscriber."""
        if not patches:
            raise EmptyPatchesError("scene: empty patches")
        applied = await self._store.apply(patches)
        wire = [Patch(path=p, value=v) for p, v in applied]
        async with self._lock:
            for sub in list(self._subscribers):
                await self._send_delta(sub, wire)

    async def reset(self) -> None:
        """Drop every subscriber and clear state. Test-harness use."""
        async with self._lock:
            subs = list(self._subscribers)
            self._subscribers.clear()
        for sub in subs:
            sub.close()
        await self._store.reset()

    async def subscribe(self, *, live: bool = False) -> tuple[Subscription, Snapshot]:
        """Attach a subscriber and return the initial snapshot atomically."""
        sub = Subscription(live=live)
        async with self._lock:
            self._subscribers.add(sub)
            state = await self._store.snapshot()
        snap = Snapshot(
            scene_id=self._id,
            scene_version=self._version,
            state=state,
            seq=sub.seq.next_server(),
        )
        return sub, snap

    async def unsubscribe(self, sub: Subscription) -> None:
        """Detach a subscriber. Idempotent."""
        async with self._lock:
            if sub in self._subscribers:
                self._subscribers.remove(sub)
        sub.close()

    async def apply_input(
        self,
        identity: Identity,
        patches: list[Patch],
    ) -> tuple[str, str] | None:
        """Validate + commit an Input frame.

        Returns ``None`` on success, or ``(error_code, message)`` when the
        frame was rejected. Validation is atomic — if any patch fails,
        none are applied.
        """
        if not patches:
            return ("INVALID_VALUE", "input: empty patches")
        for p in patches:
            if not identity.can_write(p.path):
                return ("WRITE_FORBIDDEN", f"write forbidden: {p.path}")
            if not self._accepts_input_path(identity.role, p.path):
                return ("UNKNOWN_PATH", f"unknown path: {p.path}")
            spec = self._declared_inputs.get(p.path)
            if spec is not None:
                err = check_constraint(spec, p.value)
                if err is not None:
                    return ("INVALID_VALUE", f"invalid value at {p.path}: {err}")
        as_dict = {p.path: p.value for p in patches}
        await self.emit(as_dict)
        return None

    def _accepts_input_path(self, role: Role | None, path: str) -> bool:
        """Per-namespace policy mirroring LSDP/1 § 10."""
        if has_prefix(path, "__inputs"):
            if not self._declared_inputs:
                return True
            return path in self._declared_inputs
        if has_prefix(path, "__test"):
            return role is Role.TEST
        return False

    async def _refresh_all(self) -> None:
        """Fan a fresh snapshot to every subscriber after a Set()."""
        async with self._lock:
            state = await self._store.snapshot()
            for sub in list(self._subscribers):
                sub.seq.reset()
                snap = Snapshot(
                    scene_id=self._id,
                    scene_version=self._version,
                    state=state,
                    seq=sub.seq.next_server(),
                )
                await self._send_or_drop(sub, snap)

    async def _send_delta(self, sub: Subscription, patches: list[Patch]) -> None:
        """Enqueue a Delta ; fall back to a fresh snapshot on back-pressure."""
        delta = Delta(patches=patches, seq=sub.seq.next_server())
        try:
            sub.queue.put_nowait(delta)
        except asyncio.QueueFull:
            # Buffer full — collapse to snapshot recovery.
            sub.seq.reset()
            state = await self._store.snapshot()
            snap = Snapshot(
                scene_id=self._id,
                scene_version=self._version,
                state=state,
                seq=sub.seq.next_server(),
            )
            await self._send_or_drop(sub, snap)

    async def _send_or_drop(self, sub: Subscription, msg: Any) -> None:
        try:
            sub.queue.put_nowait(msg)
        except asyncio.QueueFull:
            sub.stale = True

    async def migrate_subscribers_from(self, prev: Scene) -> list[Subscription]:
        """Move every live subscriber from ``prev`` to this scene.

        Each migrated subscriber receives a ``SceneChanged`` followed by a
        fresh ``Snapshot`` at ``seq = 1``. Returns the list of migrated
        subscriptions for caller-side accounting.
        """
        async with prev._lock:
            live = [s for s in prev._subscribers if s.live]
            for s in live:
                prev._subscribers.discard(s)
        if not live:
            return []
        async with self._lock:
            state = await self._store.snapshot()
            for sub in live:
                changed = SceneChanged(
                    scene_id=self._id,
                    scene_version=self._version,
                    seq=sub.seq.next_server(),
                )
                await self._send_or_drop(sub, changed)
                sub.seq.reset()
                snap = Snapshot(
                    scene_id=self._id,
                    scene_version=self._version,
                    state=state,
                    seq=sub.seq.next_server(),
                )
                await self._send_or_drop(sub, snap)
                self._subscribers.add(sub)
        return live
