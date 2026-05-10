"""
mrl.query
=========
Graph-traversal query layer for the law_0 particle library.

Replaces SQL JOINs with relation-edge traversal on Particle objects,
fulfilling the MRL law_0 principle: data relationships are first-class
particles, not implicit table links.

Usage
-----
    from mrl.particle_store import ParticleStore
    from mrl.query import ParticleQuery

    store = ParticleStore("/data/particle_lib")
    q     = ParticleQuery(store)

    # Get all particles of a kind
    orders = q.by_kind("orders")

    # Follow outgoing relations of a particle
    related = q.follow(orders[0], relation_kind="orders__customers")

    # BFS / DFS traversal up to N hops
    graph = q.traverse(orders[0], max_depth=2)
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Callable

from .particle import Particle
from .particle_store import ParticleStore

logger = logging.getLogger(__name__)


class ParticleQuery:
    """
    In-memory query engine for a ParticleStore.

    Loads all particles into memory on first use for fast traversal.
    For very large libraries consider building a lazy index instead.

    Parameters
    ----------
    store : ParticleStore
        The particle library to query.
    """

    def __init__(self, store: ParticleStore) -> None:
        self._store = store
        self._cache: dict[str, Particle] | None = None

    # ------------------------------------------------------------------
    # Basic lookups
    # ------------------------------------------------------------------

    def by_kind(self, kind: str) -> list[Particle]:
        """Return all particles of the given kind."""
        return self._store.load_kind(kind)

    def by_id(self, particle_id: str) -> Particle | None:
        """Return a single particle by id."""
        return self._index().get(particle_id)

    def find(self, kind: str, predicate: Callable[[Particle], bool]) -> list[Particle]:
        """
        Return all particles of ``kind`` that satisfy ``predicate``.

        Example
        -------
        ::

            q.find("orders", lambda p: p.value.get("status") == "shipped")
        """
        return [p for p in self.by_kind(kind) if predicate(p)]

    def all(self) -> list[Particle]:
        """Return every particle in the library."""
        return list(self._index().values())

    # ------------------------------------------------------------------
    # Relation traversal
    # ------------------------------------------------------------------

    def follow(
        self,
        particle: Particle,
        relation_kind: str | None = None,
    ) -> list[Particle]:
        """
        Return the particles that ``particle`` points to via its relations.

        Parameters
        ----------
        particle : Particle
            Source particle.
        relation_kind : str | None
            If given, only follow relations of this kind.
            ``None`` → follow all outgoing relations.

        Returns
        -------
        list[Particle]
            Target particles (missing targets are silently skipped).
        """
        idx = self._index()
        results: list[Particle] = []
        for rel in particle.relations:
            if relation_kind is not None and rel.kind != relation_kind:
                continue
            target = idx.get(rel.target_id)
            if target is not None:
                results.append(target)
        return results

    def back_refs(self, particle: Particle, relation_kind: str | None = None) -> list[Particle]:
        """
        Return all particles that point *to* ``particle`` (reverse traversal).

        Parameters
        ----------
        particle : Particle
            Target particle to find references to.
        relation_kind : str | None
            Filter by relation kind.

        Returns
        -------
        list[Particle]
            All particles that have a Relation pointing to ``particle.id``.
        """
        results: list[Particle] = []
        for p in self._index().values():
            for rel in p.relations:
                if rel.target_id == particle.id:
                    if relation_kind is None or rel.kind == relation_kind:
                        results.append(p)
                        break
        return results

    # ------------------------------------------------------------------
    # Graph traversal
    # ------------------------------------------------------------------

    def traverse(
        self,
        start: Particle,
        max_depth: int = 3,
        relation_kind: str | None = None,
    ) -> dict[str, Particle]:
        """
        BFS traversal from ``start``, following outgoing relations up to
        ``max_depth`` hops.

        Returns
        -------
        dict[str, Particle]
            All reachable particles keyed by id (includes ``start``).
        """
        visited: dict[str, Particle] = {}
        queue: deque[tuple[Particle, int]] = deque([(start, 0)])

        while queue:
            current, depth = queue.popleft()
            if current.id in visited:
                continue
            visited[current.id] = current
            if depth >= max_depth:
                continue
            for neighbour in self.follow(current, relation_kind=relation_kind):
                if neighbour.id not in visited:
                    queue.append((neighbour, depth + 1))

        return visited

    def shortest_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 10,
    ) -> list[Particle] | None:
        """
        BFS shortest path from ``source_id`` to ``target_id``.

        Returns the path as a list of Particles (including both endpoints),
        or ``None`` if no path exists within ``max_depth`` hops.
        """
        idx = self._index()
        start = idx.get(source_id)
        if start is None:
            return None

        # BFS with parent tracking
        parent: dict[str, str | None] = {source_id: None}
        queue: deque[tuple[Particle, int]] = deque([(start, 0)])

        while queue:
            current, depth = queue.popleft()
            if current.id == target_id:
                return _reconstruct_path(parent, idx, target_id)
            if depth >= max_depth:
                continue
            for rel in current.relations:
                if rel.target_id not in parent:
                    parent[rel.target_id] = current.id
                    neighbour = idx.get(rel.target_id)
                    if neighbour:
                        queue.append((neighbour, depth + 1))

        return None

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Invalidate the in-memory cache and reload from store."""
        self._cache = None

    def _index(self) -> dict[str, Particle]:
        if self._cache is None:
            self._cache = {p.id: p for p in self._store.load_all()}
            logger.debug("ParticleQuery: loaded %d particles into cache.", len(self._cache))
        return self._cache


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _reconstruct_path(
    parent: dict[str, str | None],
    idx: dict[str, Particle],
    target_id: str,
) -> list[Particle]:
    path: list[Particle] = []
    current_id: str | None = target_id
    while current_id is not None:
        p = idx.get(current_id)
        if p:
            path.append(p)
        current_id = parent.get(current_id)
    return list(reversed(path))
