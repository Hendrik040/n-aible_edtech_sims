"""MCP memory tools — ``recall_memory`` retrieval and ``write_summary`` write.

``recall_memory`` ports the hybrid ranking behaviour of
``backend/common/services/simulation_helper/memory_service.retrieve_memories_hybrid``
to an ``@tool``-decorated async function that plugs into an MCP server
(assembled in phase-2.7). Memory rows are read through the phase-1.2
``pgvector_store`` and filtered client-side by ``persona_id`` / ``scene_id``
metadata, since the low-level store intentionally exposes only an
``entity_type`` namespace filter.

``write_summary`` persists a scene-level conversation summary into the
``conversation_summaries`` table. Enforces one summary per
(user_progress, scene) — a second call with the same pair updates the
existing row rather than inserting a duplicate.

Contract (recall_memory):

* Input schema:  ``persona_id: int``, ``scene_id: int``, ``query: str``,
  ``k: int = 5``.
* Success return:  ``{"content": [{"type": "text", "text": ...}, ...],
  "is_error": False}`` with up to ``k`` chunks ordered best-first.
* Missing / deleted persona, or unexpected exception:
  ``{"content": [{"type": "text", "text": "<message>"}], "is_error": True}``.
  The tool never raises to the MCP runtime.
* Empty / whitespace ``query`` or non-positive ``k`` short-circuits to
  ``{"content": [], "is_error": False}`` without touching the DB.

Contract (write_summary):

* Input schema:  ``user_progress_id: int``, ``scene_id: int``,
  ``summary_text: str``.
* Success return:  ``{"content": [{"type": "text", "text": "summary saved"}],
  "structuredContent": {"id": <int>}, "is_error": False}``.
* Empty / whitespace ``summary_text``: raises ``ValueError``.
* Unexpected DB exception: ``{"content": [{"type": "text", "text":
  "<message>"}], "is_error": True}``. The tool never raises to the MCP
  runtime.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from claude_agent_sdk import tool
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.connection import SessionLocal
from common.db.models import ConversationSummaries
from common.services import pgvector_store
from common.services.embeddings_service import EmbeddingsService
from modules.simulation import repository

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]

_MEMORY_NAMESPACE = "memory"
_OVERFETCH_MULTIPLIER = 3
_MAX_OVERFETCH_MULTIPLIER = 24
_SEMANTIC_WEIGHT = 0.7
_IMPORTANCE_WEIGHT = 0.3
_DEFAULT_K = 5

_PERSONA_ERROR_MESSAGE = "Persona not found or not in scene"
_GENERIC_ERROR_MESSAGE = "Failed to recall memory"

_embeddings_service_singleton: EmbeddingsService | None = None


def _get_embeddings_service() -> EmbeddingsService:
    """Return a lazily-constructed shared embeddings service.

    Kept module-scoped so the OpenAI client is created once per process and
    so tests can monkeypatch this function to inject a mock.
    """
    global _embeddings_service_singleton
    if _embeddings_service_singleton is None:
        _embeddings_service_singleton = EmbeddingsService(client=AsyncOpenAI())
    return _embeddings_service_singleton


def _success(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"content": blocks, "is_error": False}


def _error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "is_error": True,
    }


def _extract_content(metadata: dict[str, Any]) -> str | None:
    """Return the memory text stored alongside the embedding, or ``None``.

    The pgvector store stores the original text inside ``embedding_metadata``
    because the ``vector_embeddings`` table has no dedicated content column.
    We accept ``content`` as the canonical key and fall back to
    ``memory_content`` for compatibility with memories written by the legacy
    ``memory_service``.
    """
    for key in ("content", "memory_content"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _rank_candidates(
    rows: list[dict[str, Any]],
    persona_id: int,
    scene_id: int,
) -> list[tuple[float, str]]:
    """Filter ``rows`` by persona+scene and hybrid-rank the survivors."""
    persona_key = str(persona_id)
    scene_key = str(scene_id)
    ranked: list[tuple[float, str]] = []

    for row in rows:
        metadata = row.get("embedding_metadata")
        if not isinstance(metadata, dict):
            continue
        if str(metadata.get("persona_id")) != persona_key:
            continue
        if str(metadata.get("scene_id")) != scene_key:
            continue
        content = _extract_content(metadata)
        if content is None:
            continue

        try:
            similarity = float(row.get("similarity_score", 0.0))
        except (TypeError, ValueError):
            similarity = 0.0
        try:
            importance = float(metadata.get("importance_score", 0.0))
        except (TypeError, ValueError):
            importance = 0.0

        hybrid_score = (
            _SEMANTIC_WEIGHT * similarity + _IMPORTANCE_WEIGHT * importance
        )
        ranked.append((hybrid_score, content))

    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return ranked


@tool(
    name="recall_memory",
    description=(
        "Retrieve up to k most-relevant memory chunks for a persona in a "
        "given scene using hybrid semantic + importance ranking. Returns "
        "MCP text content blocks ordered best-first. Optional integer "
        "argument 'k' (default 5) caps the number of chunks returned."
    ),
    input_schema={
        "persona_id": int,
        "scene_id": int,
        "query": str,
    },
)
async def recall_memory(args: dict[str, Any]) -> dict[str, Any]:
    """MCP tool entry point — see module docstring for the contract."""
    try:
        persona_id = args["persona_id"]
        scene_id = args["scene_id"]
        query = args.get("query", "")
        k = args.get("k", _DEFAULT_K)

        if not isinstance(k, int) or k <= 0:
            return _success([])
        if not isinstance(query, str) or not query.strip():
            return _success([])

        is_member = await asyncio.to_thread(
            repository.validate_persona_in_scene, persona_id, scene_id
        )
        if not is_member:
            return _error(_PERSONA_ERROR_MESSAGE)

        service = _get_embeddings_service()
        embed_result = await service.embed([query])
        if not embed_result or not embed_result[0]:
            return _success([])
        query_vector = embed_result[0]

        fetch_k = max(k * _OVERFETCH_MULTIPLIER, k)
        max_fetch_k = max(k * _MAX_OVERFETCH_MULTIPLIER, k)
        ranked: list[tuple[float, str]] = []
        while True:
            candidates = await pgvector_store.similarity_search(
                query_vector, _MEMORY_NAMESPACE, k=fetch_k
            )
            ranked = _rank_candidates(candidates, persona_id, scene_id)
            if (
                len(ranked) >= k
                or len(candidates) < fetch_k
                or fetch_k >= max_fetch_k
            ):
                break
            fetch_k = min(fetch_k * 2, max_fetch_k)

        blocks = [{"type": "text", "text": text} for _, text in ranked[:k]]
        return _success(blocks)
    except Exception:
        logger.exception(
            "recall_memory failed for persona_id=%s scene_id=%s",
            args.get("persona_id"),
            args.get("scene_id"),
        )
        return _error(_GENERIC_ERROR_MESSAGE)


_GENERIC_WRITE_SUMMARY_ERROR_MESSAGE = "Failed to write summary"
_SUMMARY_TYPE = "scene"


def _write_summary_sync(
    user_progress_id: int,
    scene_id: int,
    summary_text: str,
    *,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Blocking implementation of ``write_summary`` — kept out of the event loop."""
    factory = session_factory or SessionLocal
    session = factory()
    try:
        existing = session.execute(
            select(ConversationSummaries)
            .where(ConversationSummaries.user_progress_id == user_progress_id)
            .where(ConversationSummaries.scene_id == scene_id)
        ).scalar_one_or_none()

        if existing is not None:
            existing.summary_text = summary_text
            summary_id = existing.id
        else:
            row = ConversationSummaries(
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                summary_type=_SUMMARY_TYPE,
                summary_text=summary_text,
            )
            session.add(row)
            session.flush()
            summary_id = row.id

        session.commit()
        return {
            "content": [{"type": "text", "text": "summary saved"}],
            "structuredContent": {"id": summary_id},
            "is_error": False,
        }
    except Exception:
        session.rollback()
        logger.exception(
            "write_summary failed for user_progress_id=%s scene_id=%s",
            user_progress_id,
            scene_id,
        )
        return _error(_GENERIC_WRITE_SUMMARY_ERROR_MESSAGE)
    finally:
        session.close()


@tool(
    name="write_summary",
    description=(
        "Persist a scene-level conversation summary for a student's "
        "simulation run. Enforces one summary per (user_progress_id, "
        "scene_id) pair: calling again with the same pair updates the "
        "existing row. Raises ValueError for empty or whitespace-only "
        "summary_text."
    ),
    input_schema={
        "user_progress_id": int,
        "scene_id": int,
        "summary_text": str,
    },
)
async def write_summary(args: dict[str, Any]) -> dict[str, Any]:
    """MCP tool entry point for ``write_summary`` — see module docstring."""
    try:
        user_progress_id = args["user_progress_id"]
        scene_id = args["scene_id"]
        summary_text = args["summary_text"]

        if not isinstance(summary_text, str) or not summary_text.strip():
            raise ValueError("summary_text must be a non-empty string")

        return await asyncio.to_thread(
            _write_summary_sync,
            user_progress_id,
            scene_id,
            summary_text,
        )
    except ValueError:
        raise
    except Exception:
        logger.exception(
            "write_summary failed for user_progress_id=%s scene_id=%s",
            args.get("user_progress_id"),
            args.get("scene_id"),
        )
        return _error(_GENERIC_WRITE_SUMMARY_ERROR_MESSAGE)


__all__ = ["recall_memory", "write_summary"]
