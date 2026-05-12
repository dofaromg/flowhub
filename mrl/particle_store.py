"""
mrl.particle_store
==================
Particle file library — persists and loads law_0 particles on disk.

Directory layout
----------------
    <store_root>/
        index.json          ← master index: id → {kind, file}
        <kind>/
            <id>.json       ← one particle per file

Usage
-----
    from mrl.particle_store import ParticleStore

    store = ParticleStore("/data/particle_lib")
    store.write(particles)          # persist a list[Particle]

    all_particles = store.load_all()
    by_kind       = store.load_kind("orders")
    one           = store.load_one("abc123...")
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None

from .particle import Particle

logger = logging.getLogger(__name__)

_INDEX_FILE = "index.json"
_LOCK_FILE = ".index.lock"


class ParticleStore:
    """
    File-system-based particle library.

    Parameters
    ----------
    root : str | Path
        Root directory for the particle library.  Created if absent.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def write(self, particles: list[Particle]) -> None:
        """
        Persist a list of particles to the library.

        Each particle is written to ``<root>/<kind>/<id>.json``.
        The master index at ``<root>/index.json`` is updated atomically.
        Existing particles with the same id are overwritten.
        """
        with _locked_index(self.root / _LOCK_FILE):
            index = self._load_index()

            for particle in particles:
                kind_dir = self.root / _safe_name(particle.kind)
                kind_dir.mkdir(parents=True, exist_ok=True)

                file_path = kind_dir / f"{particle.id}.json"
                file_path.write_text(particle.to_json(), encoding="utf-8")

                index[particle.id] = {
                    "kind": particle.kind,
                    "file": str(file_path.relative_to(self.root)),
                }

            self._save_index(index)
        logger.info("Wrote %d particle(s) to %s.", len(particles), self.root)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load_all(self) -> list[Particle]:
        """Load every particle in the library."""
        return list(self._iter_particles(self._load_index().values()))

    def load_kind(self, kind: str) -> list[Particle]:
        """Load all particles of a specific kind (table)."""
        index = self._load_index()
        entries = [e for e in index.values() if e["kind"] == kind]
        return list(self._iter_particles(entries))

    def load_one(self, particle_id: str) -> Particle | None:
        """Load a single particle by id.  Returns ``None`` if not found."""
        index = self._load_index()
        entry = index.get(particle_id)
        if entry is None:
            return None
        return self._read_file(entry["file"])

    def count(self) -> int:
        """Return the total number of particles in the library."""
        return len(self._load_index())

    def kinds(self) -> list[str]:
        """Return the distinct kind labels present in the library."""
        index = self._load_index()
        return sorted({e["kind"] for e in index.values()})

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_index(self) -> dict:
        index_path = self.root / _INDEX_FILE
        if not index_path.exists():
            return {}
        return json.loads(index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: dict) -> None:
        index_path = self.root / _INDEX_FILE
        # Write to a temp file then rename for atomicity
        tmp_path = index_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        tmp_path.replace(index_path)

    def _iter_particles(self, entries) -> Iterator[Particle]:
        for entry in entries:
            p = self._read_file(entry["file"])
            if p is not None:
                yield p

    def _read_file(self, relative_path: str) -> Particle | None:
        full_path = self.root / relative_path
        if not full_path.exists():
            logger.warning("Particle file missing: %s", full_path)
            return None
        return Particle.from_json(full_path.read_text(encoding="utf-8"))


def _safe_name(name: str) -> str:
    """Convert a table/kind name to a filesystem-safe directory name."""
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


@contextmanager
def _locked_index(lock_path: Path) -> Iterator[None]:
    """Serialize index updates with a lock file when fcntl is available."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        else:  # pragma: no cover
            logger.debug("fcntl is unavailable; ParticleStore index writes are not process-locked.")
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
