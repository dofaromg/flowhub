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

import logging
from typing import Any

from .particle import Particle, Relation, _derive_id
from .sql_ingest import SQLIngestor

logger = logging.getLogger(__name__)


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
    particles: dict[str, Particle] = {}   # id → Particle

    for table, rows in rows_by_table.items():
        for row in rows:
            p = Particle.make(kind=table, value=_serialize_row(row))
            if p.id in particles:
                logger.warning(
                    "Duplicate particle id %s for table %r — row may be identical to another.",
                    p.id[:12],
                    table,
                )
            particles[p.id] = p

    logger.info("Created %d base particles from %d table(s).", len(particles), len(rows_by_table))

    # Step 2 — wire FK relations
    for table, table_schema in schema.items():
        fks = table_schema.get("foreign_keys", [])
        if not fks:
            continue

        rows = rows_by_table.get(table, [])
        for row in rows:
            # Find this row's particle
            src_id = _derive_id(table, _serialize_row(row))
            src_particle = particles.get(src_id)
            if src_particle is None:
                continue  # shouldn't happen

            for fk in fks:
                constrained_cols: list[str] = fk["constrained_columns"]
                referred_table: str = fk["referred_table"]
                referred_cols: list[str] = fk["referred_columns"]

                # Build the value dict of the referenced row from FK column values
                # (we only know the referenced PK values from the FK columns)
                ref_row_partial = {
                    ref_col: row.get(src_col)
                    for src_col, ref_col in zip(constrained_cols, referred_cols)
                }

                # Find matching target particle by scanning referred table rows
                target_id = _find_target_id(
                    referred_table,
                    ref_row_partial,
                    rows_by_table.get(referred_table, []),
                )

                if target_id and target_id in particles:
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

    total_relations = sum(len(p.relations) for p in particles.values())
    logger.info("Wired %d FK relation edge(s) across all particles.", total_relations)

    return list(particles.values())


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a DB row dict to a JSON-safe dict (stringify non-serialisable types)."""
    return {k: (str(v) if not _json_safe(v) else v) for k, v in row.items()}


def _json_safe(v: Any) -> bool:
    return v is None or isinstance(v, (bool, int, float, str, list, dict))


def _build_row_index(
    referred_table: str,
    candidate_rows: list[dict[str, Any]],
    key_cols: list[str],
) -> dict[tuple, str]:
    """
    Build a lookup dict from (key_col_values…) → particle_id for O(1) FK lookups.
    """
    index: dict[tuple, str] = {}
    for row in candidate_rows:
        key = tuple(row.get(col) for col in key_cols)
        index[key] = _derive_id(referred_table, _serialize_row(row))
    return index


def _find_target_id(
    referred_table: str,
    ref_pk_values: dict[str, Any],
    candidate_rows: list[dict[str, Any]],
) -> str | None:
    """
    Find the particle id of the row in ``referred_table`` whose columns
    match ``ref_pk_values``.  Returns ``None`` if not found or if any
    FK value is ``None`` (dangling reference).
    """
    if any(v is None for v in ref_pk_values.values()):
        return None
    key_cols = list(ref_pk_values.keys())
    index = _build_row_index(referred_table, candidate_rows, key_cols)
    key = tuple(ref_pk_values[col] for col in key_cols)
    return index.get(key)
