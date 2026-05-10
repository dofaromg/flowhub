"""
mrl.sql_ingest
==============
SQL ingestion module — reads relational schema and data from any
SQLAlchemy-compatible database (SQLite, PostgreSQL, MySQL, …).

Usage
-----
    from mrl.sql_ingest import SQLIngestor

    ingestor = SQLIngestor("sqlite:///mydb.sqlite")
    schema   = ingestor.get_schema()   # dict of table → column/FK metadata
    rows     = ingestor.get_rows()     # dict of table → list[dict]
"""

from __future__ import annotations

import logging
from typing import Any

try:
    import sqlalchemy as sa
    from sqlalchemy import inspect as sa_inspect
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "SQLAlchemy is required for sql_ingest. "
        "Install it with:  pip install sqlalchemy"
    ) from exc

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

ColumnMeta = dict[str, Any]   # name, type, nullable, primary_key, default
FKMeta = dict[str, str]        # constrained_columns, referred_table, referred_columns
TableSchema = dict[str, Any]   # columns, primary_keys, foreign_keys


class SQLIngestor:
    """
    Connects to a SQL database and extracts schema + row data.

    Parameters
    ----------
    dsn : str
        SQLAlchemy connection string, e.g.
        ``"sqlite:///mydb.sqlite"`` or
        ``"postgresql+psycopg2://user:pw@host/db"``.
    tables : list[str] | None
        Restrict ingestion to these table names.  ``None`` → all tables.
    """

    def __init__(self, dsn: str, tables: list[str] | None = None) -> None:
        self._engine = sa.create_engine(dsn)
        self._tables = tables

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def get_schema(self) -> dict[str, TableSchema]:
        """
        Return schema metadata for every (selected) table.

        Returns
        -------
        dict mapping table_name → TableSchema:
            {
                "columns":      [{"name": ..., "type": ..., ...}],
                "primary_keys": ["col1", ...],
                "foreign_keys": [{"constrained_columns": [...],
                                   "referred_table":      "...",
                                   "referred_columns":    [...]}],
            }
        """
        inspector = sa_inspect(self._engine)
        table_names = self._selected_tables(inspector)
        schema: dict[str, TableSchema] = {}

        for table in table_names:
            columns: list[ColumnMeta] = []
            for col in inspector.get_columns(table):
                columns.append(
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "primary_key": col.get("primary_key", False),
                        "default": str(col.get("default")) if col.get("default") is not None else None,
                    }
                )

            pk_constraint = inspector.get_pk_constraint(table)
            primary_keys: list[str] = pk_constraint.get("constrained_columns", [])

            fks: list[FKMeta] = []
            for fk in inspector.get_foreign_keys(table):
                fks.append(
                    {
                        "constrained_columns": fk["constrained_columns"],
                        "referred_table": fk["referred_table"],
                        "referred_columns": fk["referred_columns"],
                    }
                )

            schema[table] = {
                "columns": columns,
                "primary_keys": primary_keys,
                "foreign_keys": fks,
            }

        logger.info("Ingested schema for %d table(s).", len(schema))
        return schema

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------

    def get_rows(self) -> dict[str, list[dict[str, Any]]]:
        """
        Return all rows for every (selected) table as plain dicts.

        Returns
        -------
        dict mapping table_name → list of row dicts.
        """
        inspector = sa_inspect(self._engine)
        table_names = self._selected_tables(inspector)
        metadata = sa.MetaData()
        metadata.reflect(bind=self._engine, only=table_names)

        result: dict[str, list[dict[str, Any]]] = {}
        with self._engine.connect() as conn:
            for table_name in table_names:
                table_obj = metadata.tables[table_name]
                rows = conn.execute(table_obj.select()).mappings().all()
                result[table_name] = [dict(row) for row in rows]
                logger.info(
                    "Table %r: %d row(s) ingested.", table_name, len(result[table_name])
                )

        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _selected_tables(self, inspector: sa.engine.Inspector) -> list[str]:
        available = inspector.get_table_names()
        if self._tables is None:
            return available
        missing = set(self._tables) - set(available)
        if missing:
            raise ValueError(f"Table(s) not found in database: {missing}")
        return [t for t in self._tables if t in available]
