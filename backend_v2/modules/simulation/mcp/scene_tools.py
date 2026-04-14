"""Scene-progression MCP tools — ``advance_scene`` and ``complete_scene``.

``advance_scene`` moves a learner to the next scene in order.
``complete_scene`` marks the current scene as completed with a summary.

Both tools validate preconditions and return ``is_error=True`` with a
descriptive message on violation.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from claude_agent_sdk import tool
from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.connection import SessionLocal
from common.db.models import (
    SceneProgress,
    SimulationScene,
    UserProgress,
)

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


def _error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "is_error": True,
    }


def _ok(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "is_error": False,
    }


def _advance_scene_sync(
    user_progress_id: int,
    *,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    factory = session_factory or SessionLocal
    session = factory()
    try:
        user_progress = session.get(UserProgress, user_progress_id)
        if user_progress is None:
            return _error(
                f"No user_progress found for user_progress_id={user_progress_id}"
            )

        if user_progress.simulation_status == "completed":
            return _error("Simulation is already completed")

        scenes = (
            session.execute(
                select(SimulationScene)
                .where(SimulationScene.simulation_id == user_progress.simulation_id)
                .where(SimulationScene.deleted_at.is_(None))
                .order_by(SimulationScene.scene_order)
            )
            .scalars()
            .all()
        )

        current_idx = None
        for i, scene in enumerate(scenes):
            if scene.id == user_progress.current_scene_id:
                current_idx = i
                break

        if current_idx is None:
            return _error(
                f"Current scene {user_progress.current_scene_id} not found in simulation"
            )

        if current_idx >= len(scenes) - 1:
            return _ok(
                f"Already at final scene (scene_id={scenes[current_idx].id}, "
                f"title={scenes[current_idx].title!r}). No advancement possible."
            )

        next_scene = scenes[current_idx + 1]

        completed = list(user_progress.scenes_completed or [])
        completed.append(user_progress.current_scene_id)
        user_progress.scenes_completed = completed
        user_progress.current_scene_id = next_scene.id

        existing_progress = session.execute(
            select(SceneProgress)
            .where(SceneProgress.user_progress_id == user_progress_id)
            .where(SceneProgress.scene_id == next_scene.id)
        ).scalar_one_or_none()

        if existing_progress is None:
            session.add(
                SceneProgress(
                    user_progress_id=user_progress_id,
                    scene_id=next_scene.id,
                    status="in_progress",
                )
            )
        else:
            existing_progress.status = "in_progress"

        session.commit()
        return _ok(
            f"Advanced to scene_id={next_scene.id}, title={next_scene.title!r}"
        )
    except Exception:
        logger.exception(
            "advance_scene failed for user_progress_id=%s", user_progress_id
        )
        session.rollback()
        return _error("Failed to advance scene")
    finally:
        session.close()


@tool(
    name="advance_scene",
    description=(
        "Move the learner to the next scene in order. "
        "Returns the new scene ID and title on success, "
        "or a no-op message if already at the final scene."
    ),
    input_schema={
        "user_progress_id": int,
    },
)
async def advance_scene(args: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(
        _advance_scene_sync, args["user_progress_id"]
    )


def _complete_scene_sync(
    user_progress_id: int,
    scene_id: int,
    summary: str,
    *,
    session_factory: SessionFactory | None = None,
) -> dict[str, Any]:
    factory = session_factory or SessionLocal
    session = factory()
    try:
        user_progress = session.get(UserProgress, user_progress_id)
        if user_progress is None:
            return _error(
                f"No user_progress found for user_progress_id={user_progress_id}"
            )

        if user_progress.current_scene_id != scene_id:
            return _error(
                f"cannot complete scene {scene_id} when current scene is "
                f"{user_progress.current_scene_id}"
            )

        completed = list(user_progress.scenes_completed or [])
        if scene_id in completed:
            return _error(f"Scene {scene_id} is already completed")

        scene_progress = session.execute(
            select(SceneProgress)
            .where(SceneProgress.user_progress_id == user_progress_id)
            .where(SceneProgress.scene_id == scene_id)
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if scene_progress is None:
            scene_progress = SceneProgress(
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                status="completed",
                completed_at=now,
                progress_data={"summary": summary},
            )
            session.add(scene_progress)
        else:
            scene_progress.status = "completed"
            scene_progress.completed_at = now
            progress_data = dict(scene_progress.progress_data or {})
            progress_data["summary"] = summary
            scene_progress.progress_data = progress_data

        completed.append(scene_id)
        user_progress.scenes_completed = completed

        session.commit()
        return _ok(f"Scene {scene_id} marked as completed")
    except Exception:
        logger.exception(
            "complete_scene failed for user_progress_id=%s scene_id=%s",
            user_progress_id,
            scene_id,
        )
        session.rollback()
        return _error("Failed to complete scene")
    finally:
        session.close()


@tool(
    name="complete_scene",
    description=(
        "Mark the current scene as completed and store a summary. "
        "The scene_id must match the learner's current scene."
    ),
    input_schema={
        "user_progress_id": int,
        "scene_id": int,
        "summary": str,
    },
)
async def complete_scene(args: dict[str, Any]) -> dict[str, Any]:
    return await asyncio.to_thread(
        _complete_scene_sync,
        args["user_progress_id"],
        args["scene_id"],
        args["summary"],
    )


__all__ = ["advance_scene", "complete_scene"]
