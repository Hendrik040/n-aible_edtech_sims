"""Grading MCP tools — ``lookup_rubric`` retrieval and ``submit_grade`` write.

``lookup_rubric`` ports the retrieval behaviour of
``backend/common/services/simulation_helper/grading_vector_store.GradingVectorStore.search_grading_materials``
to an ``@tool``-decorated async function that plugs into an MCP server
(assembled in phase-2.7). Grading chunks live in the ``"grading"`` namespace
of the phase-1.2 ``pgvector_store``; the rows it returns include
``material_id`` but not the owning ``simulation_id``, so we resolve the set
of materials belonging to ``scenario_id`` via a focused read against the
``grading_materials`` table and filter the candidates client-side.

``submit_grade`` is the write-side companion: the grading agent calls it
with a per-criterion score map once it has finished evaluating a scene. The
tool validates that every submitted rubric key corresponds to a criterion
on the scenario's ``grading_config``, persists the result into the scene's
``scene_progress.progress_data["grading_result"]`` slot, and records one
``grading_materials`` row whose ``content`` is the JSON-serialised payload.
Both the scene-progress update and the grading-material insert are
idempotent on ``(user_progress_id, scene_id)``.

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
import json
import logging
import math
from typing import Any, Callable

from claude_agent_sdk import tool
from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.connection import SessionLocal
from common.db.models import (
    GradingMaterial,
    SceneProgress,
    Simulation,
    SimulationScene,
    UserProgress,
)
from common.services import pgvector_store
from common.services.embeddings_service import EmbeddingsService

logger = logging.getLogger(__name__)

_GRADING_NAMESPACE = "grading"
_OVERFETCH_MULTIPLIER = 3
_MAX_OVERFETCH_MULTIPLIER = 24
_DEFAULT_K = 3
_MAX_K = 50
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
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return score if math.isfinite(score) else 0.0


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
        k = min(k, _MAX_K)
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


_GRADE_RESULT_KEY = "grading_result"
_GRADE_MATERIAL_FILENAME_TEMPLATE = "grade_{user_progress_id}_{scene_id}.json"
_GRADE_MATERIAL_SUCCESS_STATUS = "completed"
_CRITERION_KEY_FIELDS = ("description", "name", "criterion_name")
_GENERIC_SUBMIT_ERROR_MESSAGE = "Failed to submit grade"
_UNKNOWN_USER_PROGRESS_TEMPLATE = (
    "No user_progress found for user_progress_id={user_progress_id}"
)
_UNKNOWN_SCENE_TEMPLATE = "No scene found for scene_id={scene_id}"
_SCENE_SIMULATION_MISMATCH_TEMPLATE = (
    "scene_id={scene_id} does not belong to simulation_id={simulation_id}"
)
_NO_RUBRIC_TEMPLATE = (
    "Simulation {simulation_id} has no grading rubric configured"
)
_REQUIRED_SUBMIT_GRADE_KEYS = (
    "user_progress_id",
    "scene_id",
    "rubric_scores",
    "strictness",
)


def _extract_rubric_keys(grading_config: dict[str, Any] | None) -> list[str]:
    """Return the ordered list of rubric-criterion keys for a simulation.

    Criteria are stored as a list under ``grading_config["criteria"]``. Each
    criterion dict is expected to expose one of ``description`` /
    ``name`` / ``criterion_name`` as its human-facing label; the first
    non-empty match wins. Any criterion missing all three fields is skipped
    silently rather than failing validation — the rubric author owns that
    structural gap.
    """
    if not isinstance(grading_config, dict):
        return []
    criteria = grading_config.get("criteria")
    if not isinstance(criteria, list):
        return []
    keys: list[str] = []
    for item in criteria:
        if not isinstance(item, dict):
            continue
        for field in _CRITERION_KEY_FIELDS:
            value = item.get(field)
            if isinstance(value, str) and value.strip():
                keys.append(value)
                break
    return keys


def _submit_grade_sync(
    user_progress_id: int,
    scene_id: int,
    rubric_scores: dict[str, Any],
    strictness: str,
    *,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    """Blocking implementation of ``submit_grade`` — kept out of the event loop.

    The async ``submit_grade`` wrapper runs this via ``asyncio.to_thread`` so
    the write does not stall the MCP server. Tests can also call it directly
    (passing a fixture ``session_factory``) to avoid spinning up an asyncio
    runner.
    """
    factory = session_factory or SessionLocal
    session = factory()
    try:
        # Lock the user_progress row so concurrent submit_grade calls for
        # the same learner serialise on Postgres; SQLite ignores FOR UPDATE
        # and is single-writer anyway, so tests are unaffected. A proper
        # DB-side upsert would require unique constraints on
        # scene_progress(user_progress_id, scene_id) and
        # grading_materials(simulation_id, filename) — schema changes that
        # are out of scope for this ticket.
        user_progress = session.get(
            UserProgress, user_progress_id, with_for_update=True
        )
        if user_progress is None:
            return _error(
                _UNKNOWN_USER_PROGRESS_TEMPLATE.format(
                    user_progress_id=user_progress_id
                )
            )
        simulation_id = user_progress.simulation_id

        scene = session.get(SimulationScene, scene_id)
        if scene is None:
            return _error(_UNKNOWN_SCENE_TEMPLATE.format(scene_id=scene_id))
        if scene.simulation_id != simulation_id:
            return _error(
                _SCENE_SIMULATION_MISMATCH_TEMPLATE.format(
                    scene_id=scene_id, simulation_id=simulation_id
                )
            )

        simulation = session.get(Simulation, simulation_id)
        rubric_keys = _extract_rubric_keys(
            simulation.grading_config if simulation is not None else None
        )
        if not rubric_keys:
            return _error(
                _NO_RUBRIC_TEMPLATE.format(simulation_id=simulation_id)
            )

        submitted_keys = set(rubric_scores.keys())
        valid_keys = set(rubric_keys)
        invalid_keys = sorted(submitted_keys - valid_keys)
        if invalid_keys:
            return _error(
                "rubric_scores contains keys not in the simulation's rubric: "
                + ", ".join(invalid_keys)
            )

        payload = {
            "user_progress_id": user_progress_id,
            "scene_id": scene_id,
            "simulation_id": simulation_id,
            "rubric_scores": dict(rubric_scores),
            "strictness": strictness,
        }

        scene_progress = session.execute(
            select(SceneProgress)
            .where(SceneProgress.user_progress_id == user_progress_id)
            .where(SceneProgress.scene_id == scene_id)
        ).scalar_one_or_none()
        if scene_progress is None:
            scene_progress = SceneProgress(
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                progress_data={_GRADE_RESULT_KEY: payload},
            )
            session.add(scene_progress)
        else:
            progress_data = dict(scene_progress.progress_data or {})
            progress_data[_GRADE_RESULT_KEY] = payload
            scene_progress.progress_data = progress_data

        filename = _GRADE_MATERIAL_FILENAME_TEMPLATE.format(
            user_progress_id=user_progress_id, scene_id=scene_id
        )
        content = json.dumps(payload, sort_keys=True)
        material = session.execute(
            select(GradingMaterial)
            .where(GradingMaterial.simulation_id == simulation_id)
            .where(GradingMaterial.filename == filename)
        ).scalar_one_or_none()
        if material is None:
            material = GradingMaterial(
                simulation_id=simulation_id,
                filename=filename,
                content=content,
                processing_status=_GRADE_MATERIAL_SUCCESS_STATUS,
            )
            session.add(material)
        else:
            material.content = content
            material.processing_status = _GRADE_MATERIAL_SUCCESS_STATUS

        session.commit()
        return {
            "content": [{"type": "text", "text": "grade recorded"}],
            "structuredContent": payload,
            "is_error": False,
        }
    except Exception:
        session.rollback()
        logger.exception(
            "submit_grade failed for user_progress_id=%s scene_id=%s",
            user_progress_id,
            scene_id,
        )
        return _error(_GENERIC_SUBMIT_ERROR_MESSAGE)
    finally:
        session.close()


@tool(
    name="submit_grade",
    description=(
        "Persist a per-criterion grade for one scene of a student's "
        "simulation run. Writes the result into that scene_progress row "
        "and records the payload as a grading_materials entry. Validates "
        "that rubric_scores keys match the simulation's configured rubric "
        "criteria; unknown keys surface as is_error=True without touching "
        "the database. Idempotent on (user_progress_id, scene_id): "
        "re-submitting updates the existing rows."
    ),
    input_schema={
        "user_progress_id": int,
        "scene_id": int,
        "rubric_scores": dict,
        "strictness": str,
    },
)
async def submit_grade(args: dict[str, Any]) -> dict[str, Any]:
    """MCP tool entry point for ``submit_grade`` — see module docstring."""
    if not isinstance(args, dict):
        logger.warning(
            "submit_grade called with non-dict args: type=%s", type(args).__name__
        )
        return _error(_GENERIC_SUBMIT_ERROR_MESSAGE)

    missing = [key for key in _REQUIRED_SUBMIT_GRADE_KEYS if key not in args]
    if missing:
        # Log only field names so per-criterion scores and identifiers from
        # the incoming payload never leak into stdout/log aggregators.
        logger.warning(
            "submit_grade missing required arguments: %s",
            ", ".join(sorted(missing)),
        )
        return _error(_GENERIC_SUBMIT_ERROR_MESSAGE)

    user_progress_id = args["user_progress_id"]
    scene_id = args["scene_id"]
    rubric_scores = args["rubric_scores"]
    strictness = args["strictness"]

    if not isinstance(rubric_scores, dict):
        return _error(
            "rubric_scores must be a dict of criterion_key -> score"
        )

    return await asyncio.to_thread(
        _submit_grade_sync,
        user_progress_id,
        scene_id,
        rubric_scores,
        strictness,
    )


__all__ = ["lookup_rubric", "submit_grade"]
