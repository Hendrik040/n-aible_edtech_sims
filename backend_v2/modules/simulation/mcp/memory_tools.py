"""``recall_memory`` MCP tool — hybrid persona+scene-scoped memory retrieval.

Ports the hybrid ranking behaviour of
``backend/common/services/simulation_helper/memory_service.retrieve_memories_hybrid``
to an ``@tool``-decorated async function that plugs into an MCP server
(assembled in phase-2.7). Persona / scene scoping is pushed down into the
``pgvector_store`` SQL query via ``metadata_filter``, so only in-scope rows
ever reach the ranker. The small constant overfetch on top of ``k`` exists
purely to give the hybrid re-ranker enough candidates to promote high-
importance memories past high-similarity ones.

Contract:

* Input schema:  ``persona_id: int``, ``scene_id: int``, ``query: str``,
  ``k: int = 5``.
* Success return:  ``{"content": [{"type": "text", "text": ...}, ...],
  "is_error": False}`` with up to ``k`` chunks ordered best-first.
* Missing / deleted persona, or unexpected exception:
  ``{"content": [{"type": "text", "text": "<message>"}], "is_error": True}``.
  The tool never raises to the MCP runtime.
* Empty / whitespace ``query`` or non-positive ``k`` short-circuits to
  ``{"content": [], "is_error": False}`` without touching the DB.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from claude_agent_sdk import tool
from openai import AsyncOpenAI

from common.services import pgvector_store
from common.services.embeddings_service import EmbeddingsService
from modules.simulation import repository

logger = logging.getLogger(__name__)

_MEMORY_NAMESPACE = "memory"
_OVERFETCH_MULTIPLIER = 3
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
) -> list[tuple[float, str]]:
    """Hybrid-rank ``rows`` by weighted semantic + importance score.

    Persona / scene scoping has already been applied by the SQL query via
    ``metadata_filter``, so this function only needs to extract content,
    compute hybrid scores, and sort.
    """
    ranked: list[tuple[float, str]] = []

    for row in rows:
        metadata = row.get("embedding_metadata")
        if not isinstance(metadata, dict):
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
        candidates = await pgvector_store.similarity_search(
            query_vector,
            _MEMORY_NAMESPACE,
            k=fetch_k,
            metadata_filter={
                "persona_id": persona_id,
                "scene_id": scene_id,
            },
        )
        ranked = _rank_candidates(candidates)

        blocks = [{"type": "text", "text": text} for _, text in ranked[:k]]
        return _success(blocks)
    except Exception:
        logger.exception(
            "recall_memory failed for persona_id=%s scene_id=%s",
            args.get("persona_id"),
            args.get("scene_id"),
        )
        return _error(_GENERIC_ERROR_MESSAGE)


__all__ = ["recall_memory"]
