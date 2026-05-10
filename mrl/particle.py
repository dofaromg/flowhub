"""
mrl.particle
============
law_0 particle schema — the atomic unit of the MRL particle file library.

Every piece of data is represented as a Particle:

    {
        "id":        "<deterministic hash>",
        "kind":      "<table_name>",
        "value":     { <column: value, ...> },
        "relations": [
            {"kind": "<fk_label>", "target_id": "<particle id>"},
            ...
        ]
    }

This breaks SQL's First Normal Form by making every row a self-describing,
schema-free object whose relationships are embedded as first-class fields.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Relation:
    """A directed edge from this particle to another particle."""

    kind: str        # e.g. "has_order", "belongs_to_customer"
    target_id: str   # id of the target Particle

    def to_dict(self) -> dict:
        return {"kind": self.kind, "target_id": self.target_id}

    @classmethod
    def from_dict(cls, data: dict) -> "Relation":
        return cls(kind=data["kind"], target_id=data["target_id"])


@dataclass
class Particle:
    """
    A law_0 particle — the foundational element of the MRL particle library.

    Attributes
    ----------
    id : str
        Deterministic SHA-256 hash derived from ``kind`` + canonical ``value``.
    kind : str
        The logical type of this particle (corresponds to a SQL table name).
    value : dict[str, Any]
        The payload — column names mapped to their values.
    relations : list[Relation]
        Outgoing relationship edges to other particles.
    """

    id: str
    kind: str
    value: dict[str, Any]
    relations: list[Relation] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def make(cls, kind: str, value: dict[str, Any]) -> "Particle":
        """Create a Particle with an auto-generated deterministic id."""
        particle_id = _derive_id(kind, value)
        return cls(id=particle_id, kind=kind, value=value)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "value": self.value,
            "relations": [r.to_dict() for r in self.relations],
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "Particle":
        relations = [Relation.from_dict(r) for r in data.get("relations", [])]
        return cls(
            id=data["id"],
            kind=data["kind"],
            value=data["value"],
            relations=relations,
        )

    @classmethod
    def from_json(cls, raw: str) -> "Particle":
        return cls.from_dict(json.loads(raw))

    def __repr__(self) -> str:
        return (
            f"Particle(id={self.id[:8]}…, kind={self.kind!r}, "
            f"fields={list(self.value.keys())}, "
            f"relations={len(self.relations)})"
        )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _derive_id(kind: str, value: dict[str, Any]) -> str:
    """
    Deterministic SHA-256 id from kind + canonically sorted value payload.

    Using JSON with sorted keys ensures the same data always yields the
    same id regardless of dict insertion order.
    """
    canonical = json.dumps({"kind": kind, "value": value}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()
