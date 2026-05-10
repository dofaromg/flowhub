"""
MRL — Molecular Relational Logic
=================================
law_0 particle file library.

Transform SQL relational data into self-describing law_0 particle units that
carry their own identity, kind, value payload, and relationship pointers —
breaking free of the fixed-schema First Normal Form paradigm.

Public API
----------
from mrl import SQLIngestor, transform, ParticleStore, ParticleQuery
"""

from .particle import Particle, Relation
from .sql_ingest import SQLIngestor
from .sql_to_law0 import transform
from .particle_store import ParticleStore
from .query import ParticleQuery

__all__ = [
    "Particle",
    "Relation",
    "SQLIngestor",
    "transform",
    "ParticleStore",
    "ParticleQuery",
]
