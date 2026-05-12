"""
mrl.__main__
============
CLI entry point for the MRL law_0 transformation pipeline.

    python -m mrl <dsn> <store_dir> [--tables T1 T2 ...]

Example
-------
    python -m mrl sqlite:///mydb.sqlite ./particle_lib
    python -m mrl sqlite:///mydb.sqlite ./particle_lib --tables orders customers
"""

from __future__ import annotations

import argparse
import logging
import sys

from .sql_ingest import SQLIngestor
from .sql_to_law0 import transform
from .particle_store import ParticleStore
from .query import ParticleQuery


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m mrl",
        description=(
            "MRL law_0 — absorb a SQL database and decompose it into "
            "a particle file library."
        ),
    )
    p.add_argument("dsn", help="SQLAlchemy DSN, e.g. sqlite:///mydb.sqlite")
    p.add_argument("store_dir", help="Directory for the particle file library")
    p.add_argument(
        "--tables", nargs="+", metavar="TABLE",
        help="Restrict ingestion to specific tables (default: all tables)"
    )
    p.add_argument(
        "--query-kind", metavar="KIND",
        help="After ingestion, print all particles of this kind"
    )
    p.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s  %(name)s  %(message)s",
    )

    # 1. Ingest
    ingestor = SQLIngestor(dsn=args.dsn, tables=args.tables or None)

    # 2. Transform
    particles = transform(ingestor)
    print(f"[mrl] Transformed {len(particles)} particle(s).")

    # 3. Store
    store = ParticleStore(args.store_dir)
    store.write(particles)
    print(f"[mrl] Particle library written to: {args.store_dir}")
    print(f"[mrl] Kinds: {store.kinds()}")

    # 4. Optional query demo
    if args.query_kind:
        q = ParticleQuery(store)
        results = q.by_kind(args.query_kind)
        print(f"\n[mrl] {len(results)} particle(s) of kind={args.query_kind!r}:")
        for p in results[:20]:   # cap output at 20
            print(" ", p)

    return 0


if __name__ == "__main__":
    sys.exit(main())
