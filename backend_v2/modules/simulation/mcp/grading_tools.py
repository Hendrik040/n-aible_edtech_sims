"""``lookup_rubric`` MCP tool — scenario-scoped grading-material retrieval.

Ports the retrieval behaviour of
``backend/common/services/simulation_helper/grading_vector_store.GradingVectorStore.search_grading_materials``
to an ``@tool``-decorated async function that plugs into an MCP server
(assembled in phase-2.7). Grading chunks live in the ``"grading"`` namespace
of the phase-1.2 ``pgvector_store``; the rows it returns include
``material_id`` but not the owning ``simulation_id``, so we resolve the set
of materials belonging to ``scenario_id`` via a focused read against the
``grading_materials`` table and filter the candidates client-side.

Contract:

* Input schema:  ``scenario_id: int``, ``query: str``, ``k: int = 3``.
* Success return:  ``{"content": [{"type": "text", "text": ...}, ...],
  "structuredContent": {"results": [...]}, "is_error": False}`` with up to
  ``k`` chunks ordered best-first. Each ``results`` entry has ``content``,
  ``material_id``, ``chunk_index``, and ``relevance_score``.
* Unknown scenario (no completed grading materials for ``scenario_id``):
  ``{"content": [{"type": "text", "text": "<message naming scenario_id>"}],
  "is_error": True}``. The tool never raises to the MCP runtime.
* Empty / whitespace ``query`` or non-positive ``k`` short-circuits to
  ``{"content": [], "structuredContent": {"results": []}, "is_error": False}``
  without touching the DB.
* Any unexpected exception is logged and surfaces as a generic error
  envelope.

``scenario_id`` maps directly to ``simulation_id`` in the underlying schema
— the rewrite uses the ``scenario`` vocabulary at the MCP boundary while
the DB still stores the row on ``simulations``/``grading_materials``.
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
from common.db.models import GradingMaterial
from common.services import pgvector_store
from common.services.embeddings_service import EmbeddingsService

logger = logging.getLogger(__name__)

_GRADING_NAMESPACE = "grading"
_OVERFETCH_MULTIPLIER = 3
_MAX_OVERFETCH_MULTIPLIER = 24
_DEFAULT_K = 3
_COMPLETED_STATUS = "completed"

_UNKNOWN_SCENARIO_TEMPLATE = (
    "No grading materials found for scenario_id={scenario_id}"
)
_GENERIC_ERROR_MESSAGE = "Failed to look up rubric"

SessionFactory = Callable[[], Session]

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


def _success(
    blocks: list[dict[str, Any]], structured: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "content": blocks,
        "structuredContent": {"results": structured},
        "is_error": False,
    }


def _error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "is_error": True,
    }


def _load_scenario_material_ids(
    scenario_id: int,
    *,
    session_factory: SessionFactory | None = None,
) -> set[int]:
    """Return the set of ``grading_materials.id`` rows for ``scenario_id``.

    Only materials whose ``processing_status`` is ``"completed"`` are
    returned — a scenario whose materials are still being embedded is
    indistinguishable from an unknown scenario for the purposes of this
    tool. Tests inject ``session_factory`` to avoid touching the real DB.
    """
    factory = session_factory or SessionLocal
    session = factory()
    try:
        stmt = select(GradingMaterial.id).where(
            GradingMaterial.simulation_id == scenario_id,
            GradingMaterial.processing_status == _COMPLETED_STATUS,
        )
        return set(session.execute(stmt).scalars().all())
    finally:
        session.close()


def _as_score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


@tool(
    name="lookup_rubric",
    description=(
        "Retrieve up to k most-relevant grading-rubric chunks for a scenario "
        "using cosine similarity over that scenario's uploaded grading "
        "materials. Returns MCP text content blocks ordered best-first plus "
        "a structured 'results' list with material_id, chunk_index, and "
        "relevance_score. Optional integer argument 'k' (default 3) caps "
        "the number of chunks returned."
    ),
    input_schema={
        "scenario_id": int,
        "query": str,
        "k": int,
    },
)
async def lookup_rubric(args: dict[str, Any]) -> dict[str, Any]:
    """MCP tool entry point — see module docstring for the contract."""
    try:
        scenario_id = args["scenario_id"]
        query = args.get("query", "")
        k = args.get("k", _DEFAULT_K)

        if not isinstance(k, int) or k <= 0:
            return _success([], [])
        if not isinstance(query, str) or not query.strip():
            return _success([], [])

        material_ids = await asyncio.to_thread(
            _load_scenario_material_ids, scenario_id
        )
        if not material_ids:
            return _error(
                _UNKNOWN_SCENARIO_TEMPLATE.format(scenario_id=scenario_id)
            )

        service = _get_embeddings_service()
        embed_result = await service.embed([query])
        if not embed_result or not embed_result[0]:
            return _success([], [])
        query_vector = embed_result[0]

        fetch_k = max(k * _OVERFETCH_MULTIPLIER, k)
        max_fetch_k = max(k * _MAX_OVERFETCH_MULTIPLIER, k)
        filtered: list[dict[str, Any]] = []
        while True:
            candidates = await pgvector_store.similarity_search(
                query_vector, _GRADING_NAMESPACE, k=fetch_k
            )
            filtered = [
                row for row in candidates
                if row.get("material_id") in material_ids
            ]
            if (
                len(filtered) >= k
                or len(candidates) < fetch_k
                or fetch_k >= max_fetch_k
            ):
                break
            fetch_k = min(fetch_k * 2, max_fetch_k)

        filtered.sort(
            key=lambda row: _as_score(row.get("similarity_score")),
            reverse=True,
        )
        top = filtered[:k]

        structured = [
            {
                "content": row.get("content", ""),
                "material_id": row.get("material_id"),
                "chunk_index": row.get("chunk_index"),
                "relevance_score": _as_score(row.get("similarity_score")),
            }
            for row in top
        ]
        blocks = [
            {"type": "text", "text": row.get("content", "")} for row in top
        ]
        return _success(blocks, structured)
    except Exception:
        logger.exception(
            "lookup_rubric failed for scenario_id=%s",
            args.get("scenario_id"),
        )
        return _error(_GENERIC_ERROR_MESSAGE)


__all__ = ["lookup_rubric"]
