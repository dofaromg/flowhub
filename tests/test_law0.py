"""
Tests for the MRL law_0 particle transformation pipeline.

Uses a temporary file-based SQLite database so multiple SQLAlchemy
connections can inspect the same schema and rows during each test.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import sqlalchemy as sa

from mrl.particle import Particle, Relation
from mrl.sql_ingest import SQLIngestor
from mrl.sql_to_law0 import transform
from mrl.particle_store import ParticleStore
from mrl.query import ParticleQuery
from mrl.__main__ import _build_parser


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_dsn(tmp_path):
    """SQLite file-based DB (SQLIngestor can't use :memory: across connections)."""
    db_path = tmp_path / "test.db"
    engine = sa.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(sa.text("""
            CREATE TABLE customers (
                id   INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                city TEXT
            )
        """))
        conn.execute(sa.text("""
            CREATE TABLE orders (
                id          INTEGER PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                product     TEXT,
                amount      REAL
            )
        """))
        conn.execute(sa.text(
            "INSERT INTO customers VALUES (1, 'Alice', 'Taipei'), "
            "(2, 'Bob', 'Tokyo')"
        ))
        conn.execute(sa.text(
            "INSERT INTO orders VALUES "
            "(10, 1, 'Widget', 9.99), "
            "(11, 1, 'Gadget', 19.99), "
            "(12, 2, 'Doohickey', 4.99)"
        ))
    return f"sqlite:///{db_path}"


@pytest.fixture
def store_dir(tmp_path):
    return tmp_path / "particle_lib"


# ---------------------------------------------------------------------------
# particle.py tests
# ---------------------------------------------------------------------------

class TestParticle:
    def test_make_creates_deterministic_id(self):
        p1 = Particle.make(kind="users", value={"id": 1, "name": "Alice"})
        p2 = Particle.make(kind="users", value={"id": 1, "name": "Alice"})
        assert p1.id == p2.id

    def test_different_values_different_ids(self):
        p1 = Particle.make(kind="users", value={"id": 1})
        p2 = Particle.make(kind="users", value={"id": 2})
        assert p1.id != p2.id

    def test_kind_affects_id(self):
        p1 = Particle.make(kind="users", value={"id": 1})
        p2 = Particle.make(kind="orders", value={"id": 1})
        assert p1.id != p2.id

    def test_to_dict_roundtrip(self):
        p = Particle.make(kind="items", value={"x": 42})
        p.relations.append(Relation(kind="items__users", target_id="abc"))
        d = p.to_dict()
        p2 = Particle.from_dict(d)
        assert p2.id == p.id
        assert p2.kind == p.kind
        assert p2.value == p.value
        assert len(p2.relations) == 1
        assert p2.relations[0].kind == "items__users"

    def test_to_json_roundtrip(self):
        p = Particle.make(kind="foo", value={"bar": "baz"})
        raw = p.to_json()
        p2 = Particle.from_json(raw)
        assert p == p2

    def test_repr_truncates_id(self):
        p = Particle.make(kind="test", value={"v": 1})
        r = repr(p)
        assert "Particle(" in r
        assert "test" in r
        # Full 64-char hex id must NOT appear; truncated form with ellipsis must
        assert p.id not in r
        assert "…" in r


# ---------------------------------------------------------------------------
# sql_ingest.py tests
# ---------------------------------------------------------------------------

class TestSQLIngestor:
    def test_get_schema_tables(self, db_dsn):
        ingestor = SQLIngestor(db_dsn)
        schema = ingestor.get_schema()
        assert "customers" in schema
        assert "orders" in schema

    def test_schema_columns(self, db_dsn):
        ingestor = SQLIngestor(db_dsn)
        schema = ingestor.get_schema()
        col_names = [c["name"] for c in schema["customers"]["columns"]]
        assert "id" in col_names
        assert "name" in col_names
        assert "city" in col_names

    def test_schema_foreign_keys(self, db_dsn):
        ingestor = SQLIngestor(db_dsn)
        schema = ingestor.get_schema()
        fks = schema["orders"]["foreign_keys"]
        assert len(fks) == 1
        assert fks[0]["referred_table"] == "customers"

    def test_get_rows_counts(self, db_dsn):
        ingestor = SQLIngestor(db_dsn)
        rows = ingestor.get_rows()
        assert len(rows["customers"]) == 2
        assert len(rows["orders"]) == 3

    def test_filter_tables(self, db_dsn):
        ingestor = SQLIngestor(db_dsn, tables=["customers"])
        rows = ingestor.get_rows()
        assert "customers" in rows
        assert "orders" not in rows

    def test_missing_table_raises(self, db_dsn):
        ingestor = SQLIngestor(db_dsn, tables=["nonexistent"])
        with pytest.raises(ValueError, match="not found"):
            ingestor.get_schema()


# ---------------------------------------------------------------------------
# sql_to_law0.py tests
# ---------------------------------------------------------------------------

class TestTransform:
    def test_particle_count(self, db_dsn):
        ingestor = SQLIngestor(db_dsn)
        particles = transform(ingestor)
        # 2 customers + 3 orders = 5 particles
        assert len(particles) == 5

    def test_particle_kinds(self, db_dsn):
        ingestor = SQLIngestor(db_dsn)
        particles = transform(ingestor)
        kinds = {p.kind for p in particles}
        assert kinds == {"customers", "orders"}

    def test_fk_relations_wired(self, db_dsn):
        ingestor = SQLIngestor(db_dsn)
        particles = transform(ingestor)
        order_particles = [p for p in particles if p.kind == "orders"]
        # Every order should have one relation pointing to a customer
        for order in order_particles:
            assert len(order.relations) == 1
            assert order.relations[0].kind == "orders__customers"

    def test_customer_particles_have_no_relations(self, db_dsn):
        ingestor = SQLIngestor(db_dsn)
        particles = transform(ingestor)
        customer_particles = [p for p in particles if p.kind == "customers"]
        for c in customer_particles:
            assert c.relations == []

    def test_relation_target_is_valid_particle(self, db_dsn):
        ingestor = SQLIngestor(db_dsn)
        particles = transform(ingestor)
        particle_ids = {p.id for p in particles}
        for p in particles:
            for rel in p.relations:
                assert rel.target_id in particle_ids

    def test_duplicate_rows_preserve_distinct_particles(self, tmp_path):
        db_path = tmp_path / "duplicates.db"
        engine = sa.create_engine(f"sqlite:///{db_path}")
        with engine.begin() as conn:
            conn.execute(sa.text("""
                CREATE TABLE events (
                    label TEXT,
                    status TEXT
                )
            """))
            conn.execute(sa.text(
                "INSERT INTO events (label, status) VALUES "
                "('deploy', 'ok'), "
                "('deploy', 'ok')"
            ))

        particles = transform(SQLIngestor(f"sqlite:///{db_path}"))

        assert len(particles) == 2
        assert len({p.id for p in particles}) == 2
        assert all(p.kind == "events" for p in particles)


# ---------------------------------------------------------------------------
# particle_store.py tests
# ---------------------------------------------------------------------------

class TestParticleStore:
    def _sample_particles(self) -> list[Particle]:
        p1 = Particle.make(kind="alpha", value={"x": 1})
        p2 = Particle.make(kind="alpha", value={"x": 2})
        p3 = Particle.make(kind="beta", value={"y": "hello"})
        p3.relations.append(Relation(kind="beta__alpha", target_id=p1.id))
        return [p1, p2, p3]

    def test_write_and_load_all(self, store_dir):
        store = ParticleStore(store_dir)
        particles = self._sample_particles()
        store.write(particles)
        loaded = store.load_all()
        assert len(loaded) == 3

    def test_load_kind(self, store_dir):
        store = ParticleStore(store_dir)
        store.write(self._sample_particles())
        alpha = store.load_kind("alpha")
        assert len(alpha) == 2
        assert all(p.kind == "alpha" for p in alpha)

    def test_load_one(self, store_dir):
        store = ParticleStore(store_dir)
        particles = self._sample_particles()
        store.write(particles)
        p = store.load_one(particles[0].id)
        assert p is not None
        assert p.id == particles[0].id

    def test_load_one_missing_returns_none(self, store_dir):
        store = ParticleStore(store_dir)
        assert store.load_one("nonexistent_id") is None

    def test_count(self, store_dir):
        store = ParticleStore(store_dir)
        store.write(self._sample_particles())
        assert store.count() == 3

    def test_kinds(self, store_dir):
        store = ParticleStore(store_dir)
        store.write(self._sample_particles())
        assert store.kinds() == ["alpha", "beta"]

    def test_index_file_created(self, store_dir):
        store = ParticleStore(store_dir)
        store.write(self._sample_particles())
        assert (store_dir / "index.json").exists()

    def test_directory_structure(self, store_dir):
        store = ParticleStore(store_dir)
        store.write(self._sample_particles())
        assert (store_dir / "alpha").is_dir()
        assert (store_dir / "beta").is_dir()

    def test_relations_preserved(self, store_dir):
        store = ParticleStore(store_dir)
        particles = self._sample_particles()
        store.write(particles)
        beta = store.load_kind("beta")[0]
        assert len(beta.relations) == 1
        assert beta.relations[0].kind == "beta__alpha"


# ---------------------------------------------------------------------------
# query.py tests
# ---------------------------------------------------------------------------

class TestParticleQuery:
    def _setup_store(self, store_dir):
        p1 = Particle.make(kind="alpha", value={"x": 1})
        p2 = Particle.make(kind="alpha", value={"x": 2})
        p3 = Particle.make(kind="beta", value={"y": "hello"})
        p3.relations.append(Relation(kind="beta__alpha", target_id=p1.id))
        store = ParticleStore(store_dir)
        store.write([p1, p2, p3])
        return store, p1, p2, p3

    def test_by_kind(self, store_dir):
        store, *_ = self._setup_store(store_dir)
        q = ParticleQuery(store)
        assert len(q.by_kind("alpha")) == 2
        assert len(q.by_kind("beta")) == 1

    def test_by_id(self, store_dir):
        store, p1, *_ = self._setup_store(store_dir)
        q = ParticleQuery(store)
        found = q.by_id(p1.id)
        assert found is not None
        assert found.id == p1.id

    def test_by_id_missing(self, store_dir):
        store, *_ = self._setup_store(store_dir)
        q = ParticleQuery(store)
        assert q.by_id("bad_id") is None

    def test_find_with_predicate(self, store_dir):
        store, *_ = self._setup_store(store_dir)
        q = ParticleQuery(store)
        results = q.find("alpha", lambda p: p.value["x"] == 1)
        assert len(results) == 1
        assert results[0].value["x"] == 1

    def test_by_kind_uses_cached_index_until_refresh(self, store_dir):
        store, *_ = self._setup_store(store_dir)
        q = ParticleQuery(store)

        assert len(q.by_kind("alpha")) == 2

        store.write([Particle.make(kind="alpha", value={"x": 3})])
        assert len(q.by_kind("alpha")) == 2

        q.refresh()
        assert len(q.by_kind("alpha")) == 3

    def test_follow_relation(self, store_dir):
        store, p1, p2, p3 = self._setup_store(store_dir)
        q = ParticleQuery(store)
        neighbours = q.follow(p3)
        assert len(neighbours) == 1
        assert neighbours[0].id == p1.id

    def test_follow_with_kind_filter(self, store_dir):
        store, p1, p2, p3 = self._setup_store(store_dir)
        q = ParticleQuery(store)
        # correct kind
        assert len(q.follow(p3, relation_kind="beta__alpha")) == 1
        # wrong kind
        assert len(q.follow(p3, relation_kind="nonexistent")) == 0

    def test_back_refs(self, store_dir):
        store, p1, p2, p3 = self._setup_store(store_dir)
        q = ParticleQuery(store)
        refs = q.back_refs(p1)
        assert len(refs) == 1
        assert refs[0].id == p3.id

    def test_traverse(self, store_dir):
        store, p1, p2, p3 = self._setup_store(store_dir)
        q = ParticleQuery(store)
        # start at p3, follow its relation to p1
        graph = q.traverse(p3, max_depth=2)
        assert p3.id in graph
        assert p1.id in graph
        assert p2.id not in graph  # p2 unreachable from p3

    def test_shortest_path_direct(self, store_dir):
        store, p1, p2, p3 = self._setup_store(store_dir)
        q = ParticleQuery(store)
        path = q.shortest_path(p3.id, p1.id)
        assert path is not None
        assert [p.id for p in path] == [p3.id, p1.id]

    def test_shortest_path_no_route(self, store_dir):
        store, p1, p2, p3 = self._setup_store(store_dir)
        q = ParticleQuery(store)
        path = q.shortest_path(p1.id, p3.id)   # no edge from p1 to p3
        assert path is None

    def test_all(self, store_dir):
        store, *_ = self._setup_store(store_dir)
        q = ParticleQuery(store)
        assert len(q.all()) == 3


class TestCLI:
    def test_tables_requires_at_least_one_value(self):
        parser = _build_parser()

        with pytest.raises(SystemExit):
            parser.parse_args(["sqlite:///tmp.db", "./particle_lib", "--tables"])
