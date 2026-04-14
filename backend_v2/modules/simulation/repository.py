"""Data-access helpers for the simulation module.

The MCP tools in :mod:`modules.simulation.mcp` go through this module rather
than importing SQLAlchemy models directly, so that query logic stays
testable and in one place. For this ticket (phase-2.1 / recall_memory) the
only query we need is a persona-in-scene membership check.
"""
from __future__ import annotations

from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from common.db.connection import SessionLocal
from common.db.models import SimulationPersona, scene_personas

SessionFactory = Callable[[], Session]


def validate_persona_in_scene(
    persona_id: int,
    scene_id: int,
    *,
    session_factory: SessionFactory | None = None,
) -> bool:
    """Return ``True`` when a non-deleted persona is linked to the scene.

    Soft-deleted personas (``deleted_at IS NOT NULL``) are treated as
    non-existent. Tests inject a ``session_factory`` to avoid touching the
    real database.
    """
    factory = session_factory or SessionLocal
    session = factory()
    try:
        stmt = (
            select(SimulationPersona.id)
            .join(
                scene_personas,
                scene_personas.c.persona_id == SimulationPersona.id,
            )
            .where(
                SimulationPersona.id == persona_id,
                scene_personas.c.scene_id == scene_id,
                SimulationPersona.deleted_at.is_(None),
            )
        )
        return session.execute(stmt).scalar_one_or_none() is not None
    finally:
        session.close()


__all__ = ["SessionFactory", "validate_persona_in_scene"]
