"""
MRL_aggregator.py — Multi-source particle aggregator (改自 fusion_engine 概念)

origin_signature : MrLiouWord
version          : 1.0
created_at       : 2026-05-11
source           : MRL_RelayStation v0.1
law              : LAW-2 ADDITIVE_RESOLUTION

Collects particle streams from multiple input sources and fuses them
into a unified particle manifest with deduplication and provenance tracking.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# Particle record
# ---------------------------------------------------------------------------

class ParticleRecord:
    """A single particle entry with provenance metadata."""

    __slots__ = ("key", "entry", "source", "absorbed_at", "content_hash")

    def __init__(self, key: str, entry: dict, source: str) -> None:
        self.key = key
        self.entry = entry
        self.source = source
        self.absorbed_at = time.time()
        canonical = json.dumps(entry, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8")
        self.content_hash = "sha256:" + hashlib.sha256(canonical).hexdigest()

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "entry": self.entry,
            "source": self.source,
            "absorbed_at": self.absorbed_at,
            "content_hash": self.content_hash,
        }


# ---------------------------------------------------------------------------
# Aggregator (particle store)
# ---------------------------------------------------------------------------

class MRLAggregator:
    """
    Content-addressed particle store that aggregates from multiple sources.

    Features:
    - CAS deduplication by content hash
    - Provenance tracking (source + timestamp)
    - Layer-indexed fast lookup
    - Export to manifest JSON
    """

    def __init__(self) -> None:
        # primary store: fl-NNN → ParticleRecord
        self._store: dict[str, ParticleRecord] = {}
        # content-hash → fl-NNN  (CAS dedup index)
        self._cas: dict[str, str] = {}
        # layer → set of fl-NNN keys
        self._layer_index: dict[str, set[str]] = defaultdict(set)

    # ------------------------------------------------------------------
    # Absorb
    # ------------------------------------------------------------------

    def absorb(self, key: str, entry: dict, source: str = "unknown") -> str:
        """
        Absorb a single particle into the store.

        If an identical particle (same content hash) already exists,
        the existing record is kept (LAW-2: additive, no deletion).

        Returns:
            'absorbed' | 'duplicate'
        """
        rec = ParticleRecord(key, entry, source)
        if rec.content_hash in self._cas:
            return "duplicate"
        self._store[key] = rec
        self._cas[rec.content_hash] = key
        layer = entry.get("layer", "L?")
        self._layer_index[layer].add(key)
        return "absorbed"

    def absorb_dict(self, dictionary: dict, source: str = "unknown") -> dict[str, int]:
        """
        Absorb a full Fluin dictionary (fl-NNN → entry).

        Returns:
            {"absorbed": N, "duplicate": N, "skipped": N}
        """
        counts: dict[str, int] = {"absorbed": 0, "duplicate": 0, "skipped": 0}
        for key, entry in dictionary.items():
            if not key.startswith("fl-"):
                counts["skipped"] += 1
                continue
            if not isinstance(entry, dict):
                counts["skipped"] += 1
                continue
            result = self.absorb(key, entry, source)
            counts[result] += 1
        return counts

    def absorb_file(self, path: Path, source: str | None = None) -> dict[str, int]:
        """Absorb a Fluin dictionary JSON file."""
        p = Path(path)
        data = json.loads(p.read_text(encoding="utf-8"))
        src = source or p.name
        entries = {k: v for k, v in data.items() if k.startswith("fl-")}
        return self.absorb_dict(entries, src)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get(self, key: str) -> ParticleRecord | None:
        """Retrieve a particle by fl-NNN key."""
        return self._store.get(key)

    def by_layer(self, layer: str) -> list[ParticleRecord]:
        """Return all particles in a given layer (e.g. 'L0')."""
        return [self._store[k] for k in sorted(self._layer_index.get(layer, set()))]

    def by_concept(self, concept: str) -> ParticleRecord | None:
        """Fuzzy-find first particle whose concept matches (case-insensitive)."""
        q = concept.lower()
        for rec in self._store.values():
            if rec.entry.get("concept", "").lower() == q:
                return rec
        return None

    def search(self, query: str) -> list[ParticleRecord]:
        """
        Simple full-text search across concept, zh, q4, q8, fp16 fields.
        Returns matches sorted by key.
        """
        q = query.lower()
        results: list[ParticleRecord] = []
        for rec in self._store.values():
            e = rec.entry
            haystack = " ".join([
                e.get("concept", ""),
                e.get("zh", ""),
                e.get("q4", ""),
                e.get("q8", ""),
                e.get("fp16", ""),
            ]).lower()
            if q in haystack:
                results.append(rec)
        return sorted(results, key=lambda r: r.key)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        """Return store statistics."""
        return {
            "total_particles": len(self._store),
            "unique_hashes": len(self._cas),
            "layers": {layer: len(keys) for layer, keys in self._layer_index.items()},
            "sources": list({r.source for r in self._store.values()}),
        }

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def to_manifest(self) -> dict:
        """
        Export the aggregated store as a particle manifest.

        The manifest includes all particle records with provenance metadata,
        suitable for signing with MRL_verifier.sign_manifest().
        """
        return {
            "mrl_manifest_version": "1.0",
            "origin_signature": "MrLiouWord",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "stats": self.stats(),
            "particles": {key: rec.to_dict() for key, rec in sorted(self._store.items())},
        }

    def save_manifest(self, path: Path) -> None:
        """Write manifest JSON to path."""
        Path(path).write_text(
            json.dumps(self.to_manifest(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    def to_dict(self) -> dict:
        """Export as a plain fl-NNN → entry dict (same format as Fluin.Dict.Base.json)."""
        return {key: rec.entry for key, rec in sorted(self._store.items())}

    def save_dict(self, path: Path) -> None:
        """Write as Fluin dictionary JSON to path."""
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# Module-level default aggregator
# ---------------------------------------------------------------------------

_default_agg = MRLAggregator()


def get_aggregator() -> MRLAggregator:
    """Return the module-level default aggregator."""
    return _default_agg


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="MRL Aggregator — absorb and query particle stores"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_absorb = sub.add_parser("absorb", help="Absorb a dictionary JSON file")
    p_absorb.add_argument("file", help="Path to Fluin.Dict.Base.json")
    p_absorb.add_argument("--source", default=None)
    p_absorb.add_argument("--out-manifest", default=None, help="Save manifest to file")
    p_absorb.add_argument("--out-dict", default=None, help="Save merged dict to file")

    p_search = sub.add_parser("search", help="Search particles")
    p_search.add_argument("query")
    p_search.add_argument("--file", default=None, help="Dictionary file to load first")
    p_search.add_argument("--lod", default="q8", choices=["symbol", "q4", "q8", "fp16"])

    p_stats = sub.add_parser("stats", help="Print store statistics")
    p_stats.add_argument("--file", default=None)

    args = parser.parse_args()
    agg = MRLAggregator()

    if args.cmd == "absorb":
        counts = agg.absorb_file(Path(args.file), source=args.source)
        print(f"✅ Absorbed: {counts}")
        print(json.dumps(agg.stats(), indent=2))
        if args.out_manifest:
            agg.save_manifest(Path(args.out_manifest))
            print(f"   Manifest saved → {args.out_manifest}")
        if args.out_dict:
            agg.save_dict(Path(args.out_dict))
            print(f"   Dict saved → {args.out_dict}")

    elif args.cmd == "search":
        if args.file:
            agg.absorb_file(Path(args.file))
        results = agg.search(args.query)
        if not results:
            print("No matches.")
            sys.exit(1)
        for r in results:
            lod_val = r.entry.get(args.lod, r.entry.get("concept", "?"))
            print(f"  {r.key}  {r.entry.get('concept','?'):15}  {r.entry.get('zh',''):6}  {lod_val}")

    elif args.cmd == "stats":
        if args.file:
            agg.absorb_file(Path(args.file))
        print(json.dumps(agg.stats(), indent=2))
