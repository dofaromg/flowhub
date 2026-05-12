"""
mrl.sql_to_law0
===============
Transformer — converts SQL schema + row data into law_0 Particle objects.

Each SQL table row becomes one Particle of kind=<table_name>.
Each foreign-key constraint becomes a Relation edge embedded in the
referencing particle.  This dissolves the rigid relational schema into
a flat cloud of self-describing particles.

Usage
-----
    from mrl.sql_ingest import SQLIngestor
    from mrl.sql_to_law0 import transform

    ingestor = SQLIngestor("sqlite:///mydb.sqlite")
    particles = transform(ingestor)
    # → list[Particle]
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from .particle import Particle, Relation
from .sql_ingest import SQLIngestor

logger = logging.getLogger(__name__)

LookupKey = tuple[Any, ...]  # foreign-key column values in lookup order
FKLookupIndex = dict[LookupKey, list[str]]  # lookup key → matching particle ids
FKLookupIndexes = dict[tuple[str, tuple[str, ...]], FKLookupIndex]  # per target table/key set


def transform(ingestor: SQLIngestor) -> list[Particle]:
    """
    Ingest a SQL database and return a flat list of law_0 Particles.

    Algorithm
    ---------
    1.  Read schema (columns, primary keys, foreign keys).
    2.  Read all rows for every table.
    3.  For each row, build a Particle(kind=table, value=row_dict).
    4.  For each FK constraint in the schema, embed a Relation edge
        inside the referencing particle pointing to the referenced particle.

    Parameters
    ----------
    ingestor : SQLIngestor
        A configured SQLIngestor connected to the target database.

    Returns
    -------
    list[Particle]
        All particles produced from the database, with relations populated.
    """
    schema = ingestor.get_schema()
    rows_by_table = ingestor.get_rows()

    # Step 1 — build base particles (no relations yet)
    particles_by_id: dict[str, Particle] = {}  # final particle id → Particle
    row_particles: dict[tuple[str, int], Particle] = {}  # (table, row_index) → Particle
    duplicate_counts: dict[tuple[str, str], int] = {}  # (table, base_id) → duplicate count

    for table, rows in rows_by_table.items():
        for row_idx, row in enumerate(rows):
            p = Particle.make(kind=table, value=_serialize_row(row))
            duplicate_key = (table, p.id)
            duplicate_count = duplicate_counts.get(duplicate_key, 0)
            if duplicate_count:
                p.id = _derive_duplicate_id(p.id, duplicate_count)
                logger.warning(
                    "Duplicate particle id %s for table %r — assigning distinct duplicate id.",
                    p.id[:12],
                    table,
                )
            duplicate_counts[duplicate_key] = duplicate_count + 1
            particles_by_id[p.id] = p
            row_particles[(table, row_idx)] = p

    logger.info(
        "Created %d base particles from %d table(s).",
        len(particles_by_id),
        len(rows_by_table),
    )

    fk_target_indexes = _build_fk_target_indexes(schema, rows_by_table, row_particles)

    # Step 2 — wire FK relations
    for table, table_schema in schema.items():
        fks = table_schema.get("foreign_keys", [])
        if not fks:
            continue

        rows = rows_by_table.get(table, [])
        for row_idx, row in enumerate(rows):
            # Find this row's particle
            src_particle = row_particles[(table, row_idx)]

            for fk in fks:
                constrained_cols: list[str] = fk["constrained_columns"]
                referred_table = fk["referred_table"]
                referred_cols: list[str] = fk["referred_columns"]
                if not referred_table or not constrained_cols or not referred_cols:
                    continue

                # Build the value dict of the referenced row from FK column values
                # (we only know the referenced PK values from the FK columns)
                ref_row_partial = {
                    ref_col: row.get(src_col)
                    for src_col, ref_col in zip(constrained_cols, referred_cols)
                }

                # Find matching target particle by scanning referred table rows
                target_id = _find_target_id(
                    ref_row_partial,
                    fk_target_indexes.get((referred_table, tuple(referred_cols)), {}),
                )

                if target_id and target_id in particles_by_id:
                    rel_kind = f"{table}__{referred_table}"
                    relation = Relation(kind=rel_kind, target_id=target_id)
                    # Avoid duplicate relations
                    if relation not in src_particle.relations:
                        src_particle.relations.append(relation)
                elif target_id is None:
                    logger.debug(
                        "FK from %r to %r: no matching target found for %s.",
                        table,
                        referred_table,
                        ref_row_partial,
                    )

    total_relations = sum(len(p.relations) for p in particles_by_id.values())
    logger.info("Wired %d FK relation edge(s) across all particles.", total_relations)

    return list(particles_by_id.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DB row dict to a JSON-safe dict (stringify non-serialisable types)."""
    return {k: (str(v) if not _json_safe(v) else v) for k, v in row.items()}


def _json_safe(v: Any) -> bool:
    return v is None or isinstance(v, (bool, int, float, str, list, dict))


def _build_fk_target_index(
    referred_table: str,
    candidate_rows: list[dict[str, Any]],
    key_cols: list[str],
    row_particles: dict[tuple[str, int], Particle],
) -> FKLookupIndex:
    """
    Build a lookup dict from (key_col_values…) → particle_id for O(1) FK lookups.
    """
    index: FKLookupIndex = {}
    for row_idx, row in enumerate(candidate_rows):
        key = tuple(row.get(col) for col in key_cols)
        particle = row_particles[(referred_table, row_idx)]
        index.setdefault(key, []).append(particle.id)
    return index


def _build_fk_target_indexes(
    schema: dict[str, Any],
    rows_by_table: dict[str, list[dict[str, Any]]],
    row_particles: dict[tuple[str, int], Particle],
) -> FKLookupIndexes:
    indexes: FKLookupIndexes = {}
    for table_schema in schema.values():
        for fk in table_schema.get("foreign_keys", []):
            referred_table = fk["referred_table"]
            referred_cols = tuple(fk["referred_columns"])
            if not referred_table or not referred_cols:
                continue
            index_key = (referred_table, referred_cols)
            if index_key not in indexes:
                indexes[index_key] = _build_fk_target_index(
                    referred_table,
                    rows_by_table.get(referred_table, []),
                    list(referred_cols),
                    row_particles,
                )
    return indexes


def _find_target_id(
    ref_pk_values: dict[str, Any],
    index: FKLookupIndex,
) -> str | None:
    """
    Find the particle id of the row in ``referred_table`` whose columns
    match ``ref_pk_values``.  Returns ``None`` if not found or if any
    FK value is ``None`` (dangling reference).
    """
    if any(v is None for v in ref_pk_values.values()):
        return None
    key = tuple(ref_pk_values[col] for col in ref_pk_values)
    matches = index.get(key)
    if not matches:
        return None
    return matches[0]


def _derive_duplicate_id(base_id: str, duplicate_count: int) -> str:
    """Derive a stable unique id for a duplicate row from its base id and occurrence count."""
    return hashlib.sha256(f"{base_id}:{duplicate_count}".encode("utf-8")).hexdigest()
