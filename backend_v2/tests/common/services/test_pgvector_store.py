"""Tests for :mod:`common.services.pgvector_store`.

These tests exercise the module against a real PostgreSQL instance with the
``vector`` extension enabled. A disposable database is created per-session
so that repeated runs do not leak state.

The test database URL comes from the ``PGVECTOR_TEST_DATABASE_URL`` env var
(falling back to ``TEST_DATABASE_URL``). When neither is set the tests skip
cleanly — the module's verification gate is documented on the ticket as
requiring a disposable Postgres fixture.
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from common.services.pgvector_store import (
    DEFAULT_K,
    SUPPORTED_NAMESPACES,
    UnsupportedFilterError,
    UnsupportedNamespaceError,
    _build_metadata_filter_sql,
    _format_vector_literal,
    similarity_search,
    upsert,
)


def _resolve_test_database_url() -> str | None:
    """Return the URL to a Postgres instance with pgvector, or None to skip."""
    return (
        os.environ.get("PGVECTOR_TEST_DATABASE_URL")
        or os.environ.get("TEST_DATABASE_URL")
    )


_DB_URL = _resolve_test_database_url()

pytestmark = pytest.mark.skipif(
    _DB_URL is None,
    reason=(
        "Set PGVECTOR_TEST_DATABASE_URL (or TEST_DATABASE_URL) to a Postgres "
        "instance with the pgvector extension to run pgvector_store tests."
    ),
)


@pytest.fixture(scope="session")
def pgvector_engine() -> Iterator[Engine]:
    """Session-scoped engine against the disposable Postgres instance.

    Creates the ``vector`` extension and a minimal schema mirroring
    ``vector_embeddings`` and ``grading_material_chunks`` — including the
    ``grading_materials`` parent row referenced by the FK. The schema uses
    JSON columns (matching production) so that the service's JSON→vector
    casts are exercised end-to-end.
    """
    assert _DB_URL is not None  # guarded by pytestmark
    # Safeguard: this fixture runs destructive DROP TABLE/VIEW statements
    # against canonical table names (``vector_embeddings`` /
    # ``grading_material_chunks``). Refuse to run if the target database URL
    # does not look like a disposable test database, to avoid wiping real data
    # if someone points ``PGVECTOR_TEST_DATABASE_URL`` at a shared instance.
    if "test" not in _DB_URL.lower() and os.environ.get("PGVECTOR_TEST_FORCE") != "1":
        pytest.skip(
            "Refusing to run destructive pgvector fixture against a database "
            "whose URL does not contain 'test'. Set PGVECTOR_TEST_FORCE=1 to "
            "override."
        )
    engine = create_engine(_DB_URL)

    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    except OperationalError as exc:
        pytest.skip(f"Postgres unavailable at {_DB_URL!r}: {exc}")

    schema_prefix = f"pgvector_test_{uuid.uuid4().hex[:8]}"
    ve_table = f"{schema_prefix}_vector_embeddings"
    gm_table = f"{schema_prefix}_grading_materials"
    gmc_table = f"{schema_prefix}_grading_material_chunks"

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE {ve_table} (
                    id SERIAL PRIMARY KEY,
                    entity_type VARCHAR NOT NULL,
                    entity_id INTEGER NOT NULL,
                    embedding_vector JSON,
                    embedding_model VARCHAR,
                    embedding_metadata JSON,
                    created_at TIMESTAMP WITH TIME ZONE
                        DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE {gm_table} (
                    id SERIAL PRIMARY KEY,
                    filename VARCHAR NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE {gmc_table} (
                    id SERIAL PRIMARY KEY,
                    material_id INTEGER NOT NULL REFERENCES {gm_table}(id),
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding_vector JSON,
                    embedding_model VARCHAR,
                    embedding_dimension INTEGER,
                    content_hash VARCHAR
                )
                """
            )
        )
        # The service targets the canonical table names; point them at the
        # per-session test tables via updatable views so multiple concurrent
        # test runs can't stomp on each other.
        conn.execute(text("DROP VIEW IF EXISTS vector_embeddings CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS vector_embeddings CASCADE"))
        conn.execute(
            text(f"CREATE VIEW vector_embeddings AS SELECT * FROM {ve_table}")
        )
        conn.execute(text("DROP VIEW IF EXISTS grading_material_chunks CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS grading_material_chunks CASCADE"))
        conn.execute(
            text(
                "CREATE VIEW grading_material_chunks AS "
                f"SELECT * FROM {gmc_table}"
            )
        )

    engine.test_tables = {  # type: ignore[attr-defined]
        "vector_embeddings": ve_table,
        "grading_materials": gm_table,
        "grading_material_chunks": gmc_table,
    }

    try:
        yield engine
    finally:
        with engine.begin() as conn:
            conn.execute(text("DROP VIEW IF EXISTS vector_embeddings CASCADE"))
            conn.execute(
                text("DROP VIEW IF EXISTS grading_material_chunks CASCADE")
            )
            conn.execute(text(f"DROP TABLE IF EXISTS {gmc_table} CASCADE"))
            conn.execute(text(f"DROP TABLE IF EXISTS {gm_table} CASCADE"))
            conn.execute(text(f"DROP TABLE IF EXISTS {ve_table} CASCADE"))
        engine.dispose()


@pytest.fixture
def session_factory(pgvector_engine: Engine):
    """Per-test sessionmaker with tables truncated between tests."""
    tables = pgvector_engine.test_tables  # type: ignore[attr-defined]
    with pgvector_engine.begin() as conn:
        conn.execute(
            text(
                f"TRUNCATE TABLE {tables['grading_material_chunks']} "
                f"RESTART IDENTITY CASCADE"
            )
        )
        conn.execute(
            text(
                f"TRUNCATE TABLE {tables['grading_materials']} "
                f"RESTART IDENTITY CASCADE"
            )
        )
        conn.execute(
            text(
                f"TRUNCATE TABLE {tables['vector_embeddings']} "
                f"RESTART IDENTITY CASCADE"
            )
        )
    return sessionmaker(bind=pgvector_engine, autoflush=False)


@pytest.fixture
def seed_grading_material(pgvector_engine: Engine) -> int:
    tables = pgvector_engine.test_tables  # type: ignore[attr-defined]
    with pgvector_engine.begin() as conn:
        material_id = conn.execute(
            text(
                f"INSERT INTO {tables['grading_materials']} (filename) "
                "VALUES ('rubric.pdf') RETURNING id"
            )
        ).scalar_one()
    return int(material_id)


def _unit_vector(dim: int, axis: int) -> list[float]:
    vec = [0.0] * dim
    vec[axis] = 1.0
    return vec


def test_format_vector_literal_round_trips() -> None:
    assert _format_vector_literal([1.0, 0.0, -0.5]) == "[1,0,-0.5]"


def test_unsupported_namespace_raises() -> None:
    assert "memory" in SUPPORTED_NAMESPACES
    with pytest.raises(UnsupportedNamespaceError):
        import asyncio

        asyncio.run(
            similarity_search([0.1, 0.2], "not-a-real-namespace", k=1)
        )


@pytest.mark.asyncio
async def test_similarity_search_returns_topk_ordered(session_factory) -> None:
    """Inserted vectors come back ordered by cosine similarity, capped to ``k``."""
    # Seed five distinct unit vectors along different axes.
    for axis in range(5):
        await upsert(
            embedding=_unit_vector(8, axis),
            metadata={"entity_id": 100 + axis, "label": f"axis-{axis}"},
            namespace="memory",
            session_factory=session_factory,
        )

    query = _unit_vector(8, 2)  # closest to entity_id=102, exact match
    results = await similarity_search(
        query_embedding=query,
        namespace="memory",
        k=3,
        session_factory=session_factory,
    )

    assert len(results) == 3
    # Closest result is the exact unit vector at axis 2.
    assert results[0]["entity_id"] == 102
    assert results[0]["similarity_score"] == pytest.approx(1.0, abs=1e-6)
    # All other axes are orthogonal — cosine similarity ≈ 0.
    for row in results[1:]:
        assert row["similarity_score"] == pytest.approx(0.0, abs=1e-6)
    # Ordering is monotonically non-increasing.
    scores = [row["similarity_score"] for row in results]
    assert scores == sorted(scores, reverse=True)
    # Requested result keys are present.
    for row in results:
        assert set(row).issuperset(
            {"id", "entity_type", "entity_id", "similarity_score"}
        )


@pytest.mark.asyncio
async def test_similarity_search_filters_by_namespace(session_factory) -> None:
    """Results must only include rows whose ``entity_type`` matches the namespace."""
    # Same vector payload, three different namespaces.
    vec = _unit_vector(4, 0)
    for namespace, entity_id in (
        ("memory", 1),
        ("conversation", 2),
        ("scene", 3),
    ):
        await upsert(
            embedding=vec,
            metadata={"entity_id": entity_id},
            namespace=namespace,
            session_factory=session_factory,
        )

    # Also insert an unrelated vector into the queried namespace to confirm
    # the result comes from that namespace and not a cross-namespace leak.
    await upsert(
        embedding=_unit_vector(4, 1),
        metadata={"entity_id": 99},
        namespace="conversation",
        session_factory=session_factory,
    )

    results = await similarity_search(
        query_embedding=vec,
        namespace="conversation",
        k=DEFAULT_K,
        session_factory=session_factory,
    )

    returned_namespaces = {row["entity_type"] for row in results}
    assert returned_namespaces == {"conversation"}
    returned_ids = {row["entity_id"] for row in results}
    assert returned_ids == {2, 99}


@pytest.mark.asyncio
async def test_upsert_inserts_row_with_metadata(
    session_factory, seed_grading_material: int
) -> None:
    """Upsert writes the embedding and metadata to the correct backing table."""
    # vector_embeddings branch
    row_id = await upsert(
        embedding=[0.1, 0.2, 0.3, 0.4],
        metadata={
            "entity_id": 42,
            "embedding_model": "text-embedding-3-small",
            "origin": "unit-test",
        },
        namespace="scene",
        session_factory=session_factory,
    )
    assert row_id.isdigit()

    with session_factory() as session:  # type: Session
        row = session.execute(
            text(
                "SELECT entity_type, entity_id, embedding_vector, "
                "       embedding_model, embedding_metadata "
                "FROM vector_embeddings WHERE id = :id"
            ),
            {"id": int(row_id)},
        ).mappings().one()

    assert row["entity_type"] == "scene"
    assert row["entity_id"] == 42
    assert row["embedding_model"] == "text-embedding-3-small"
    # JSON column may come back as a parsed list or as a JSON string depending
    # on the driver — normalise before comparing.
    stored_vec = row["embedding_vector"]
    if isinstance(stored_vec, str):
        stored_vec = json.loads(stored_vec)
    assert stored_vec == [0.1, 0.2, 0.3, 0.4]
    stored_meta = row["embedding_metadata"]
    if isinstance(stored_meta, str):
        stored_meta = json.loads(stored_meta)
    assert stored_meta == {"origin": "unit-test"}

    # grading_material_chunks branch
    grading_id = await upsert(
        embedding=[0.5, 0.6, 0.7, 0.8],
        metadata={
            "material_id": seed_grading_material,
            "content_hash": "sha256:abc123",
            "chunk_index": 7,
            "content": "rubric excerpt",
            "embedding_model": "text-embedding-3-small",
        },
        namespace="grading",
        session_factory=session_factory,
    )
    assert grading_id.isdigit()

    with session_factory() as session:
        chunk = session.execute(
            text(
                "SELECT material_id, chunk_index, content, content_hash, "
                "       embedding_model, embedding_dimension "
                "FROM grading_material_chunks WHERE id = :id"
            ),
            {"id": int(grading_id)},
        ).mappings().one()

    assert chunk["material_id"] == seed_grading_material
    assert chunk["chunk_index"] == 7
    assert chunk["content"] == "rubric excerpt"
    assert chunk["content_hash"] == "sha256:abc123"
    assert chunk["embedding_dimension"] == 4


@pytest.mark.asyncio
async def test_upsert_is_idempotent_on_same_key(
    session_factory, seed_grading_material: int
) -> None:
    """Re-upserting the same idempotency key updates in place instead of duplicating."""
    # vector_embeddings idempotency on (entity_type, entity_id)
    first = await upsert(
        embedding=[0.1, 0.2, 0.3],
        metadata={"entity_id": 7, "version": 1},
        namespace="memory",
        session_factory=session_factory,
    )
    second = await upsert(
        embedding=[0.9, 0.8, 0.7],
        metadata={"entity_id": 7, "version": 2},
        namespace="memory",
        session_factory=session_factory,
    )

    assert first != second  # DELETE+INSERT yields a new SERIAL id

    with session_factory() as session:
        rows = session.execute(
            text(
                "SELECT id, embedding_metadata FROM vector_embeddings "
                "WHERE entity_type = 'memory' AND entity_id = 7"
            )
        ).mappings().all()

    assert len(rows) == 1
    assert str(rows[0]["id"]) == second
    stored_meta = rows[0]["embedding_metadata"]
    if isinstance(stored_meta, str):
        stored_meta = json.loads(stored_meta)
    assert stored_meta == {"version": 2}

    # grading idempotency on (material_id, content_hash)
    g_first = await upsert(
        embedding=[1.0, 0.0],
        metadata={
            "material_id": seed_grading_material,
            "content_hash": "sha256:deadbeef",
            "content": "v1",
        },
        namespace="grading",
        session_factory=session_factory,
    )
    g_second = await upsert(
        embedding=[0.0, 1.0],
        metadata={
            "material_id": seed_grading_material,
            "content_hash": "sha256:deadbeef",
            "content": "v2",
        },
        namespace="grading",
        session_factory=session_factory,
    )
    assert g_first != g_second
    with session_factory() as session:
        grading_rows = session.execute(
            text(
                "SELECT id, content FROM grading_material_chunks "
                "WHERE material_id = :mid AND content_hash = :ch"
            ),
            {"mid": seed_grading_material, "ch": "sha256:deadbeef"},
        ).mappings().all()

    assert len(grading_rows) == 1
    assert str(grading_rows[0]["id"]) == g_second
    assert grading_rows[0]["content"] == "v2"


@pytest.mark.asyncio
async def test_similarity_search_grading_namespace(
    session_factory, seed_grading_material: int
) -> None:
    """Grading namespace queries the grading_material_chunks table."""
    # Seed two grading chunks with orthogonal unit vectors.
    await upsert(
        embedding=_unit_vector(4, 0),
        metadata={
            "material_id": seed_grading_material,
            "content_hash": "hash-a",
            "chunk_index": 0,
            "content": "alpha",
        },
        namespace="grading",
        session_factory=session_factory,
    )
    await upsert(
        embedding=_unit_vector(4, 1),
        metadata={
            "material_id": seed_grading_material,
            "content_hash": "hash-b",
            "chunk_index": 1,
            "content": "beta",
        },
        namespace="grading",
        session_factory=session_factory,
    )

    results = await similarity_search(
        query_embedding=_unit_vector(4, 0),
        namespace="grading",
        k=2,
        session_factory=session_factory,
    )

    assert len(results) == 2
    # Closest is the identical unit vector → content "alpha".
    assert results[0]["content"] == "alpha"
    assert results[0]["similarity_score"] == pytest.approx(1.0, abs=1e-6)
    assert results[1]["content"] == "beta"
    # Each result dict carries grading-specific columns.
    for row in results:
        assert set(row).issuperset(
            {"id", "material_id", "chunk_index", "content", "content_hash"}
        )


# ---- Non-DB argument validation (help push coverage ≥85%) --------------


def test_similarity_search_rejects_empty_embedding() -> None:
    import asyncio

    with pytest.raises(ValueError):
        asyncio.run(similarity_search([], "memory", k=3))


def test_similarity_search_returns_empty_when_k_not_positive(session_factory) -> None:
    import asyncio

    assert asyncio.run(
        similarity_search(
            [0.1, 0.2],
            "memory",
            k=0,
            session_factory=session_factory,
        )
    ) == []


def test_upsert_rejects_empty_embedding() -> None:
    import asyncio

    with pytest.raises(ValueError):
        asyncio.run(upsert([], {"entity_id": 1}, "memory"))


def test_upsert_rejects_non_dict_metadata() -> None:
    import asyncio

    with pytest.raises(TypeError):
        asyncio.run(upsert([0.1], "not-a-dict", "memory"))  # type: ignore[arg-type]


def test_upsert_requires_entity_id_for_vector_embeddings(session_factory) -> None:
    import asyncio

    with pytest.raises(ValueError, match="entity_id"):
        asyncio.run(
            upsert(
                [0.1, 0.2],
                {},
                "memory",
                session_factory=session_factory,
            )
        )


def test_upsert_requires_material_id_and_hash_for_grading(session_factory) -> None:
    import asyncio

    with pytest.raises(ValueError, match="material_id"):
        asyncio.run(
            upsert(
                [0.1, 0.2],
                {"content_hash": "abc"},
                "grading",
                session_factory=session_factory,
            )
        )


# ---- metadata_filter — pure unit + DB-backed tests ---------------------


def test_build_metadata_filter_sql_empty() -> None:
    """No filter yields an empty SQL fragment and no params."""
    assert _build_metadata_filter_sql(None) == ("", {})
    assert _build_metadata_filter_sql({}) == ("", {})


def test_build_metadata_filter_sql_single_and_multi_key() -> None:
    """Filter compiles to ``AND``-joined ``->>`` equality clauses."""
    sql_one, params_one = _build_metadata_filter_sql({"persona_id": 7})
    assert sql_one == " AND embedding_metadata ->> 'persona_id' = :_mf_0"
    assert params_one == {"_mf_0": "7"}

    sql_two, params_two = _build_metadata_filter_sql(
        {"persona_id": 7, "scene_id": 42}
    )
    assert sql_two == (
        " AND embedding_metadata ->> 'persona_id' = :_mf_0"
        " AND embedding_metadata ->> 'scene_id' = :_mf_1"
    )
    assert params_two == {"_mf_0": "7", "_mf_1": "42"}


def test_build_metadata_filter_sql_rejects_unsafe_key() -> None:
    """Non-identifier keys are refused so the dynamic SQL stays safe."""
    for bad_key in ("persona id", "persona-id", "'; DROP--", "", 123):
        with pytest.raises(UnsupportedFilterError):
            _build_metadata_filter_sql({bad_key: "1"})  # type: ignore[dict-item]


def test_build_metadata_filter_sql_booleans_use_json_text() -> None:
    """Booleans serialize to lowercase ``'true'``/``'false'`` to match ``->>``."""
    sql_true, params_true = _build_metadata_filter_sql({"is_active": True})
    assert sql_true == " AND embedding_metadata ->> 'is_active' = :_mf_0"
    assert params_true == {"_mf_0": "true"}

    sql_false, params_false = _build_metadata_filter_sql({"is_active": False})
    assert sql_false == " AND embedding_metadata ->> 'is_active' = :_mf_0"
    assert params_false == {"_mf_0": "false"}


def test_build_metadata_filter_sql_none_uses_is_null() -> None:
    """``None`` emits ``IS NULL`` (``->>`` returns SQL NULL for JSON null)."""
    sql, params = _build_metadata_filter_sql({"scene_id": None})
    assert sql == " AND embedding_metadata ->> 'scene_id' IS NULL"
    assert params == {}

    # Mixed with other values: IS NULL clause coexists with bound params.
    sql_mix, params_mix = _build_metadata_filter_sql(
        {"scene_id": None, "persona_id": 7}
    )
    assert sql_mix == (
        " AND embedding_metadata ->> 'scene_id' IS NULL"
        " AND embedding_metadata ->> 'persona_id' = :_mf_1"
    )
    assert params_mix == {"_mf_1": "7"}


def test_build_metadata_filter_sql_rejects_non_scalar_value() -> None:
    """Non-JSON-scalar values (list/dict/etc.) are refused."""
    for bad_value in ([1, 2], {"nested": 1}, object()):
        with pytest.raises(UnsupportedFilterError):
            _build_metadata_filter_sql({"persona_id": bad_value})  # type: ignore[dict-item]


def test_similarity_search_rejects_metadata_filter_on_grading() -> None:
    """The grading table has no metadata column, so filters are refused."""
    import asyncio

    with pytest.raises(UnsupportedFilterError):
        asyncio.run(
            similarity_search(
                [0.1, 0.2],
                "grading",
                k=1,
                metadata_filter={"persona_id": 1},
            )
        )


@pytest.mark.asyncio
async def test_similarity_search_metadata_filter_scopes_by_key(
    session_factory,
) -> None:
    """SQL-level ``metadata_filter`` narrows results to matching rows only."""
    # Seed three memories with identical vectors but different persona_ids.
    for idx, persona_id in enumerate((1, 2, 1)):
        await upsert(
            embedding=_unit_vector(4, 0),
            metadata={
                "entity_id": 100 + idx,
                "persona_id": persona_id,
                "scene_id": 10,
                "content": f"memory-{idx}-p{persona_id}",
            },
            namespace="memory",
            session_factory=session_factory,
        )

    # No filter → all three rows come back.
    unfiltered = await similarity_search(
        query_embedding=_unit_vector(4, 0),
        namespace="memory",
        k=10,
        session_factory=session_factory,
    )
    assert len(unfiltered) == 3

    # Filter persona_id=1 → only the two persona-1 rows.
    filtered = await similarity_search(
        query_embedding=_unit_vector(4, 0),
        namespace="memory",
        k=10,
        metadata_filter={"persona_id": 1},
        session_factory=session_factory,
    )
    assert len(filtered) == 2
    for row in filtered:
        meta = row["embedding_metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        assert str(meta["persona_id"]) == "1"

    # Combined persona_id + scene_id filter also works.
    combo = await similarity_search(
        query_embedding=_unit_vector(4, 0),
        namespace="memory",
        k=10,
        metadata_filter={"persona_id": 2, "scene_id": 10},
        session_factory=session_factory,
    )
    assert len(combo) == 1
    assert combo[0]["entity_id"] == 101


@pytest.mark.asyncio
async def test_similarity_search_metadata_filter_matches_numeric_and_string(
    session_factory,
) -> None:
    """``->>`` returns text, so JSON numbers and JSON strings both match.

    This keeps the filter tolerant of writers that serialize ids differently.
    """
    await upsert(
        embedding=_unit_vector(4, 0),
        metadata={
            "entity_id": 1,
            "persona_id": 5,  # JSON number
            "content": "numeric-key",
        },
        namespace="memory",
        session_factory=session_factory,
    )
    await upsert(
        embedding=_unit_vector(4, 0),
        metadata={
            "entity_id": 2,
            "persona_id": "5",  # JSON string
            "content": "string-key",
        },
        namespace="memory",
        session_factory=session_factory,
    )

    results = await similarity_search(
        query_embedding=_unit_vector(4, 0),
        namespace="memory",
        k=10,
        metadata_filter={"persona_id": 5},
        session_factory=session_factory,
    )
    assert len(results) == 2


@pytest.mark.asyncio
async def test_similarity_search_metadata_filter_matches_bool_and_null(
    session_factory,
) -> None:
    """Bool and None filter values match PostgreSQL's JSON text semantics.

    ``->>`` returns ``'true'``/``'false'`` for JSON booleans and SQL ``NULL``
    for JSON null, so Python ``True``/``False``/``None`` must be handled
    explicitly rather than stringified as ``'True'``/``'False'``/``'None'``.
    """
    await upsert(
        embedding=_unit_vector(4, 0),
        metadata={
            "entity_id": 1,
            "is_active": True,
            "scene_id": 10,
            "content": "active-with-scene",
        },
        namespace="memory",
        session_factory=session_factory,
    )
    await upsert(
        embedding=_unit_vector(4, 0),
        metadata={
            "entity_id": 2,
            "is_active": False,
            "scene_id": None,
            "content": "inactive-no-scene",
        },
        namespace="memory",
        session_factory=session_factory,
    )

    active = await similarity_search(
        query_embedding=_unit_vector(4, 0),
        namespace="memory",
        k=10,
        metadata_filter={"is_active": True},
        session_factory=session_factory,
    )
    assert [row["entity_id"] for row in active] == [1]

    inactive = await similarity_search(
        query_embedding=_unit_vector(4, 0),
        namespace="memory",
        k=10,
        metadata_filter={"is_active": False},
        session_factory=session_factory,
    )
    assert [row["entity_id"] for row in inactive] == [2]

    no_scene = await similarity_search(
        query_embedding=_unit_vector(4, 0),
        namespace="memory",
        k=10,
        metadata_filter={"scene_id": None},
        session_factory=session_factory,
    )
    assert [row["entity_id"] for row in no_scene] == [2]
