from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest

from modules.simulation.prompts.persona_system import build_persona_system_prompt


@dataclass
class FakePersona:
    name: str = "Test Persona"
    role: str = "Chief Operating Officer"
    background: Optional[str] = "Veteran operations leader with 20 years experience."
    current_context: Optional[str] = "Facing a supply-chain crisis."
    correlation: Optional[str] = "Direct supervisor of the student."
    personality_traits: Optional[Dict[str, int]] = None
    primary_goals: Optional[List[str]] = None
    knowledge_areas: Optional[List[str]] = None
    communication_style: Optional[str] = "Direct and no-nonsense."
    system_prompt: Optional[str] = None


def _default_scene_context() -> dict:
    return {
        "simulation": {
            "title": "Supply Chain Disruption",
            "description": "A global electronics company faces critical shortages.",
            "challenge": "Resolve the chip shortage before Q4 production deadline.",
            "student_role": "a junior supply-chain analyst",
        },
        "current_scene": {
            "title": "Emergency Board Meeting",
            "description": "The board convenes to assess the crisis.",
            "objectives": ["Present risk assessment", "Propose mitigation plan"],
        },
    }


# ── Required test: test_big_five_high_openness_rendered ──────────────────────

def test_big_five_high_openness_rendered():
    persona = FakePersona(personality_traits={"openness": 9})
    result = build_persona_system_prompt(persona, _default_scene_context())
    assert "highly creative and intellectually adventurous" in result


# ── Required test: test_big_five_low_openness_rendered ───────────────────────

def test_big_five_low_openness_rendered():
    persona = FakePersona(personality_traits={"openness": 3})
    result = build_persona_system_prompt(persona, _default_scene_context())
    assert "prefers established methods" in result


# ── Required test: test_snapshot_eight_trait_permutations ────────────────────

_EIGHT_PERMUTATIONS = [
    {"openness": 10, "conscientiousness": 10, "extraversion": 10, "agreeableness": 10, "neuroticism": 10},
    {"openness": 1, "conscientiousness": 1, "extraversion": 1, "agreeableness": 1, "neuroticism": 1},
    {"openness": 5, "conscientiousness": 5, "extraversion": 5, "agreeableness": 5, "neuroticism": 5},
    {"openness": 9, "conscientiousness": 2, "extraversion": 7, "agreeableness": 4, "neuroticism": 6},
    {"openness": 3, "conscientiousness": 8, "extraversion": 1, "agreeableness": 10, "neuroticism": 2},
    {"openness": 7, "conscientiousness": 6, "extraversion": 4, "agreeableness": 3, "neuroticism": 9},
    {},
    {"openness": 5, "extraversion": 8},
]


@pytest.mark.parametrize(
    "traits, case_id",
    [(t, i) for i, t in enumerate(_EIGHT_PERMUTATIONS)],
    ids=[f"perm-{i}" for i in range(len(_EIGHT_PERMUTATIONS))],
)
def test_snapshot_eight_trait_permutations(traits, case_id, snapshot):
    persona = FakePersona(
        name=f"Persona-{case_id}",
        role="Manager",
        background="Background text.",
        personality_traits=traits or None,
    )
    result = build_persona_system_prompt(persona, _default_scene_context())
    assert result == snapshot


# ── Required test: test_scene_context_appears_in_output ──────────────────────

def test_scene_context_appears_in_output():
    persona = FakePersona(personality_traits={"openness": 5})
    ctx = _default_scene_context()
    result = build_persona_system_prompt(persona, ctx)

    assert "Supply Chain Disruption" in result
    assert "a junior supply-chain analyst" in result
    assert "Emergency Board Meeting" in result
    assert "Present risk assessment" in result
    assert "Propose mitigation plan" in result


def test_scene_context_sparse():
    persona = FakePersona(personality_traits={"openness": 5})
    sparse_ctx: dict = {}
    result = build_persona_system_prompt(persona, sparse_ctx)
    assert "PERSONA IDENTITY" not in result or "You are Test Persona" in result
    assert "RULES" in result


def test_custom_system_prompt_used():
    persona = FakePersona(system_prompt="You are a grizzled sea captain.")
    result = build_persona_system_prompt(persona, _default_scene_context())
    assert "PERSONA IDENTITY:" in result
    assert "grizzled sea captain" in result
    assert "BACKGROUND:" not in result
