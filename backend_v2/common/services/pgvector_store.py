"""Direct SQL pgvector store for ``vector_embeddings`` and ``grading_material_chunks``.

Replaces the LangChain ``PGVector`` wrapper with focused async helpers that
execute parameterised SQL through the existing ``SessionLocal`` factory.
The table schema is unchanged — embeddings live in JSON columns — so the
queries cast ``(embedding_vector::text)::vector`` at read time to use
pgvector's native ``<=>`` cosine-distance operator.

Blocking DB work is dispatched through :func:`asyncio.to_thread` so the
public API is ``async def`` without introducing an async driver.

Public surface:

    await similarity_search(query_embedding, namespace, k=5)
    await upsert(embedding, metadata, namespace)

Supported namespaces:

    "memory" | "conversation" | "scene"  → ``vector_embeddings`` filtered by
                                            ``entity_type``
    "grading"                            → ``grading_material_chunks``
                                            keyed by ``(material_id,
                                            content_hash)``
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from common.db.connection import SessionLocal

_VECTOR_EMBEDDING_NAMESPACES: frozenset[str] = frozenset(
    {"memory", "conversation", "scene"}
)
_GRADING_NAMESPACE = "grading"
SUPPORTED_NAMESPACES: frozenset[str] = (
    _VECTOR_EMBEDDING_NAMESPACES | frozenset({_GRADING_NAMESPACE})
)

DEFAULT_K = 5

SessionFactory = Callable[[], Session]

_METADATA_FILTER_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class UnsupportedNamespaceError(ValueError):
    """Raised when a namespace does not map to a known table."""


class UnsupportedFilterError(ValueError):
    """Raised when a metadata filter is invalid or unsupported for the namespace."""


def _validate_namespace(namespace: str) -> None:
    if namespace not in SUPPORTED_NAMESPACES:
        raise UnsupportedNamespaceError(
            f"namespace {namespace!r} not in {sorted(SUPPORTED_NAMESPACES)}"
        )


def _format_vector_literal(vec: list[float]) -> str:
    """Format a ``list[float]`` as a pgvector text literal (``[a,b,c]``)."""
    return "[" + ",".join(format(float(x), ".17g") for x in vec) + "]"


def _build_metadata_filter_sql(
    metadata_filter: dict[str, Any] | None,
) -> tuple[str, dict[str, str]]:
    """Compile a metadata filter dict into ``AND``-joined SQL + bind params.

    Values are compared via ``embedding_metadata ->> 'key' = :param`` so that
    metadata stored as JSON numbers *or* JSON strings both match when the
    caller passes the equivalent Python value (``->>`` always returns text).
    Keys are validated to be simple identifiers — they are interpolated into
    the SQL string because JSON key accessors cannot be bound parameters.

    Booleans serialize to lowercase ``'true'``/``'false'`` to match the text
    ``->>`` returns for JSON booleans, and ``None`` emits ``IS NULL`` since
    ``->>`` yields SQL ``NULL`` for JSON null (an ``=`` comparison never
    matches).
    """
    if not metadata_filter:
        return "", {}
    clauses: list[str] = []
    params: dict[str, str] = {}
    for idx, (key, value) in enumerate(metadata_filter.items()):
        if not isinstance(key, str) or not _METADATA_FILTER_KEY_RE.match(key):
            raise UnsupportedFilterError(
                f"metadata_filter key {key!r} must match "
                f"{_METADATA_FILTER_KEY_RE.pattern}"
            )
        if value is None:
            clauses.append(f"embedding_metadata ->> '{key}' IS NULL")
            continue
        if isinstance(value, bool):
            serialized = "true" if value else "false"
        elif isinstance(value, (str, int, float)):
            serialized = str(value)
        else:
            raise UnsupportedFilterError(
                f"metadata_filter value for {key!r} must be a JSON scalar "
                f"(str, int, float, bool, or None); got {type(value).__name__}"
            )
        param_name = f"_mf_{idx}"
        clauses.append(f"embedding_metadata ->> '{key}' = :{param_name}")
        params[param_name] = serialized
    return " AND " + " AND ".join(clauses), params


async def similarity_search(
    query_embedding: list[float],
    namespace: str,
    k: int = DEFAULT_K,
    *,
    metadata_filter: dict[str, Any] | None = None,
    session_factory: SessionFactory | None = None,
) -> list[dict]:
    """Return the ``k`` nearest rows for ``namespace``, ordered closest first.

    Each result dict contains ``id``, identifier/content columns for the
    backing table, and ``similarity_score`` = ``1 - cosine_distance``.
    Returns ``[]`` when ``k <= 0``.

    ``metadata_filter`` is an optional mapping of ``embedding_metadata``
    field→value equality constraints applied in SQL. Supported only for
    vector-embedding namespaces (``memory`` / ``conversation`` / ``scene``),
    since the grading table has no metadata column.
    """
    _validate_namespace(namespace)
    if not query_embedding:
        raise ValueError("query_embedding must be a non-empty list of floats")
    if k <= 0:
        return []
    if metadata_filter and namespace == _GRADING_NAMESPACE:
        raise UnsupportedFilterError(
            "metadata_filter is not supported for the 'grading' namespace"
        )

    factory = session_factory or SessionLocal
    return await asyncio.to_thread(
        _similarity_search_sync,
        factory,
        query_embedding,
        namespace,
        k,
        metadata_filter,
    )


async def upsert(
    embedding: list[float],
    metadata: dict,
    namespace: str,
    *,
    session_factory: SessionFactory | None = None,
) -> str:
    """Insert or update a single embedding row and return its id as a string.

    Idempotency keys (no schema change, so upsert is emulated in a single
    transaction via DELETE + INSERT):
      - ``vector_embeddings``   → ``(entity_type, entity_id)``
        requires ``metadata['entity_id']``
      - ``grading_material_chunks`` → ``(material_id, content_hash)``
        requires ``metadata['material_id']`` and ``metadata['content_hash']``
    """
    _validate_namespace(namespace)
    if not embedding:
        raise ValueError("embedding must be a non-empty list of floats")
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dict")

    factory = session_factory or SessionLocal
    return await asyncio.to_thread(
        _upsert_sync, factory, embedding, metadata, namespace
    )


def _similarity_search_sync(
    factory: SessionFactory,
    query_embedding: list[float],
    namespace: str,
    k: int,
    metadata_filter: dict[str, Any] | None,
) -> list[dict]:
    vec = _format_vector_literal(query_embedding)
    session = factory()
    try:
        if namespace == _GRADING_NAMESPACE:
            sql = text(
                """
                SELECT id,
                       material_id,
                       chunk_index,
                       content,
                       content_hash,
                       1 - ((embedding_vector::text)::vector
                             <=> CAST(:vec AS vector)) AS similarity_score
                FROM grading_material_chunks
                WHERE embedding_vector IS NOT NULL
                ORDER BY (embedding_vector::text)::vector
                         <=> CAST(:vec AS vector)
                LIMIT :k
                """
            )
            params: dict[str, Any] = {"vec": vec, "k": k}
        else:
            meta_sql, meta_params = _build_metadata_filter_sql(metadata_filter)
            sql = text(
                f"""
                SELECT id,
                       entity_type,
                       entity_id,
                       embedding_metadata,
                       1 - ((embedding_vector::text)::vector
                             <=> CAST(:vec AS vector)) AS similarity_score
                FROM vector_embeddings
                WHERE entity_type = :ns
                  AND embedding_vector IS NOT NULL{meta_sql}
                ORDER BY (embedding_vector::text)::vector
                         <=> CAST(:vec AS vector)
                LIMIT :k
                """
            )
            params = {"vec": vec, "ns": namespace, "k": k, **meta_params}

        rows = session.execute(sql, params).mappings().all()
        return [dict(row) for row in rows]
    finally:
        session.close()


def _upsert_sync(
    factory: SessionFactory,
    embedding: list[float],
    metadata: dict,
    namespace: str,
) -> str:
    session = factory()
    try:
        if namespace == _GRADING_NAMESPACE:
            new_id = _upsert_grading_chunk(session, embedding, metadata)
        else:
            new_id = _upsert_vector_embedding(session, embedding, metadata, namespace)
        session.commit()
        return str(new_id)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _upsert_vector_embedding(
    session: Session,
    embedding: list[float],
    metadata: dict,
    namespace: str,
) -> int:
    entity_id = metadata.get("entity_id")
    if entity_id is None:
        raise ValueError(
            "vector_embeddings namespaces require 'entity_id' in metadata"
        )

    embedding_model = metadata.get("embedding_model")
    extra_metadata = {
        key: value
        for key, value in metadata.items()
        if key not in {"entity_id", "embedding_model"}
    }

    session.execute(
        text(
            "DELETE FROM vector_embeddings "
            "WHERE entity_type = :ns AND entity_id = :eid"
        ),
        {"ns": namespace, "eid": entity_id},
    )
    return session.execute(
        text(
            """
            INSERT INTO vector_embeddings
                (entity_type, entity_id, embedding_vector,
                 embedding_model, embedding_metadata)
            VALUES (:ns, :eid, CAST(:vec AS json),
                    :model, CAST(:meta AS json))
            RETURNING id
            """
        ),
        {
            "ns": namespace,
            "eid": entity_id,
            "vec": json.dumps(embedding),
            "model": embedding_model,
            "meta": json.dumps(extra_metadata) if extra_metadata else None,
        },
    ).scalar_one()


def _upsert_grading_chunk(
    session: Session,
    embedding: list[float],
    metadata: dict,
) -> int:
    material_id = metadata.get("material_id")
    content_hash = metadata.get("content_hash")
    if material_id is None or content_hash is None:
        raise ValueError(
            "grading namespace requires 'material_id' and 'content_hash' "
            "in metadata"
        )

    session.execute(
        text(
            "DELETE FROM grading_material_chunks "
            "WHERE material_id = :mid AND content_hash = :ch"
        ),
        {"mid": material_id, "ch": content_hash},
    )
    return session.execute(
        text(
            """
            INSERT INTO grading_material_chunks
                (material_id, chunk_index, content,
                 embedding_vector, embedding_model, embedding_dimension,
                 content_hash)
            VALUES (:mid, :cidx, :content,
                    CAST(:vec AS json), :model, :dim, :ch)
            RETURNING id
            """
        ),
        {
            "mid": material_id,
            "cidx": metadata.get("chunk_index", 0),
            "content": metadata.get("content", ""),
            "vec": json.dumps(embedding),
            "model": metadata.get("embedding_model"),
            "dim": len(embedding),
            "ch": content_hash,
        },
    ).scalar_one()


__all__ = [
    "DEFAULT_K",
    "SUPPORTED_NAMESPACES",
    "UnsupportedFilterError",
    "UnsupportedNamespaceError",
    "similarity_search",
    "upsert",
]
