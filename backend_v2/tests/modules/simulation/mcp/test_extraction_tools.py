"""Unit tests for the MCP extraction tools (phase-2.6).

All three tools are pure parsers — no external dependencies to mock.
"""
from __future__ import annotations

import json

import pytest

from modules.simulation.mcp.extraction_tools import (
    extract_objectives,
    extract_personas,
    extract_scenes,
)

# ---------------------------------------------------------------------------
# Fixtures — reusable valid payloads
# ---------------------------------------------------------------------------

VALID_PERSONA_PAYLOAD = {
    "title": "Global Supply Chain Crisis",
    "description": "A simulation about logistics management",
    "student_role": "Operations Manager",
    "key_figures": [
        {
            "name": "Alice Chen",
            "role": "VP of Logistics",
            "background": "20 years in supply chain",
            "current_context": "Managing disrupted routes",
            "correlation": "Direct report to student",
            "personality_traits": {
                "analytical": 8,
                "creative": 5,
                "assertive": 7,
            },
            "primary_goals": ["Reduce costs", "Maintain SLA"],
            "knowledge_areas": ["Logistics", "Procurement"],
            "communication_style": "Direct and data-driven",
            "is_main_character": True,
        },
        {
            "name": "Bob Martinez",
            "role": "Warehouse Manager",
            "background": "10 years warehouse ops",
            "primary_goals": ["Optimize throughput"],
        },
    ],
}

VALID_SCENES = [
    {
        "title": "Scene 2: Escalation",
        "description": "Things get worse",
        "personas_involved": ["Alice Chen"],
        "user_goal": "De-escalate",
        "goal": "Resolve the conflict",
        "success_metric": "Tension reduced",
        "sequence_order": 2,
    },
    {
        "title": "Scene 1: Introduction",
        "description": "Meet the team",
        "personas_involved": ["Alice Chen", "Bob Martinez"],
        "user_goal": "Learn the situation",
        "goal": "Understand the crisis",
        "success_metric": "Asked 3 questions",
        "sequence_order": 1,
    },
]

VALID_OBJECTIVES = [
    "Understand supply chain risk management",
    "Apply negotiation techniques in high-pressure scenarios",
    "Evaluate trade-offs between cost and service level",
]


# ---------------------------------------------------------------------------
# extract_personas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_personas_parses_valid_json():
    result = await extract_personas.handler(
        {"pdf_text": json.dumps(VALID_PERSONA_PAYLOAD)}
    )
    assert result["is_error"] is False
    personas = json.loads(result["content"][0]["text"])
    assert len(personas) == 2
    assert personas[0]["name"] == "Alice Chen"
    assert personas[1]["name"] == "Bob Martinez"
    assert personas[0]["personality_traits"]["analytical"] == 8


@pytest.mark.asyncio
async def test_extract_personas_returns_error_on_malformed_json():
    result = await extract_personas.handler({"pdf_text": "{ broken json !!!"})
    assert result["is_error"] is True
    assert "Invalid JSON" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_extract_personas_handles_markdown_fences():
    fenced = "```json\n" + json.dumps(VALID_PERSONA_PAYLOAD) + "\n```"
    result = await extract_personas.handler({"pdf_text": fenced})
    assert result["is_error"] is False
    personas = json.loads(result["content"][0]["text"])
    assert len(personas) == 2


@pytest.mark.asyncio
async def test_extract_personas_validation_error_missing_required():
    incomplete = {"title": "X", "description": "Y"}
    result = await extract_personas.handler({"pdf_text": json.dumps(incomplete)})
    assert result["is_error"] is True
    assert "Validation error" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_extract_personas_empty_input():
    result = await extract_personas.handler({"pdf_text": ""})
    assert result["is_error"] is True


@pytest.mark.asyncio
async def test_extract_personas_optional_fields_omitted():
    minimal = {
        "title": "T",
        "description": "D",
        "student_role": "S",
        "key_figures": [{"name": "A", "role": "R"}],
    }
    result = await extract_personas.handler({"pdf_text": json.dumps(minimal)})
    assert result["is_error"] is False
    personas = json.loads(result["content"][0]["text"])
    assert personas[0] == {"name": "A", "role": "R"}


# ---------------------------------------------------------------------------
# extract_scenes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_scenes_returns_ordered_list():
    result = await extract_scenes.handler({"pdf_text": json.dumps(VALID_SCENES)})
    assert result["is_error"] is False
    scenes = json.loads(result["content"][0]["text"])
    assert scenes[0]["sequence_order"] == 1
    assert scenes[1]["sequence_order"] == 2
    assert scenes[0]["title"] == "Scene 1: Introduction"


@pytest.mark.asyncio
async def test_extract_scenes_parses_valid_array():
    single = [
        {
            "title": "S1",
            "description": "D",
            "sequence_order": 0,
        }
    ]
    result = await extract_scenes.handler({"pdf_text": json.dumps(single)})
    assert result["is_error"] is False
    scenes = json.loads(result["content"][0]["text"])
    assert len(scenes) == 1


@pytest.mark.asyncio
async def test_extract_scenes_returns_error_on_malformed_json():
    result = await extract_scenes.handler({"pdf_text": "[{bad"})
    assert result["is_error"] is True
    assert "Invalid JSON" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_extract_scenes_validation_error_missing_title():
    bad_scene = [{"description": "D", "sequence_order": 1}]
    result = await extract_scenes.handler({"pdf_text": json.dumps(bad_scene)})
    assert result["is_error"] is True
    assert "Validation error" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_extract_scenes_empty_array():
    result = await extract_scenes.handler({"pdf_text": "[]"})
    assert result["is_error"] is False
    scenes = json.loads(result["content"][0]["text"])
    assert scenes == []


@pytest.mark.asyncio
async def test_extract_scenes_negative_sequence_order():
    bad = [{"title": "T", "description": "D", "sequence_order": -1}]
    result = await extract_scenes.handler({"pdf_text": json.dumps(bad)})
    assert result["is_error"] is True
    assert "Validation error" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_extract_scenes_handles_markdown_fences():
    fenced = "```json\n" + json.dumps(VALID_SCENES) + "\n```"
    result = await extract_scenes.handler({"pdf_text": fenced})
    assert result["is_error"] is False
    scenes = json.loads(result["content"][0]["text"])
    assert len(scenes) == 2


# ---------------------------------------------------------------------------
# extract_objectives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_objectives_validates_schema():
    result = await extract_objectives.handler(
        {"pdf_text": json.dumps(VALID_OBJECTIVES)}
    )
    assert result["is_error"] is False
    objectives = json.loads(result["content"][0]["text"])
    assert objectives == VALID_OBJECTIVES


@pytest.mark.asyncio
async def test_extract_objectives_returns_error_on_non_string_items():
    mixed = ["valid", 42, "also valid"]
    result = await extract_objectives.handler({"pdf_text": json.dumps(mixed)})
    assert result["is_error"] is True
    assert "index 1" in result["content"][0]["text"]
    assert "int" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_extract_objectives_returns_error_on_malformed_json():
    result = await extract_objectives.handler({"pdf_text": "not json at all"})
    assert result["is_error"] is True


@pytest.mark.asyncio
async def test_extract_objectives_empty_array():
    result = await extract_objectives.handler({"pdf_text": "[]"})
    assert result["is_error"] is False
    objectives = json.loads(result["content"][0]["text"])
    assert objectives == []


@pytest.mark.asyncio
async def test_extract_objectives_handles_markdown_fences():
    fenced = "```\n" + json.dumps(VALID_OBJECTIVES) + "\n```"
    result = await extract_objectives.handler({"pdf_text": fenced})
    assert result["is_error"] is False
    objectives = json.loads(result["content"][0]["text"])
    assert len(objectives) == 3


@pytest.mark.asyncio
async def test_extract_objectives_nested_objects_rejected():
    bad = [{"not": "a string"}]
    result = await extract_objectives.handler({"pdf_text": json.dumps(bad)})
    assert result["is_error"] is True
    assert "dict" in result["content"][0]["text"]
