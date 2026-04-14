"""MCP tools for extracting personas, scenes, and objectives from Claude output.

Each tool receives a string (typically a Claude response containing JSON),
extracts the JSON payload, validates it against the appropriate Pydantic
schema, and returns the result in an MCP envelope.  The tools themselves
make no LLM calls — they are pure parsers/validators invoked by the
extraction orchestrator (phase-4.3).

Contract (all three tools):

* Input:  ``{"pdf_text": "<claude response containing JSON>"}``
* Success: ``{"content": [{"type": "text", "text": "<json>"}], "is_error": False}``
* Failure: ``{"content": [{"type": "text", "text": "<message>"}], "is_error": True}``
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from claude_agent_sdk import tool
from pydantic import ValidationError

from modules.simulation.mcp.schemas import (
    PersonaExtractionResult,
    SceneSchema,
)

logger = logging.getLogger(__name__)

_JSON_OBJECT_RE = re.compile(r"(\{[\s\S]*\})")
_JSON_ARRAY_RE = re.compile(r"(\[[\s\S]*\])")


def _strip_markdown_fences(text: str) -> str:
    """Remove optional markdown code fences wrapping JSON."""
    stripped = text.strip()
    if stripped.startswith("```"):
        first_newline = stripped.find("\n")
        if first_newline != -1:
            stripped = stripped[first_newline + 1 :]
        if stripped.rstrip().endswith("```"):
            stripped = stripped.rstrip()[:-3]
    return stripped.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    """Extract the first JSON object from *text*."""
    cleaned = _strip_markdown_fences(text)
    match = _JSON_OBJECT_RE.search(cleaned)
    if not match:
        raise ValueError("No JSON object found in input")
    return json.loads(match.group(1))


def _extract_json_array(text: str) -> list[Any]:
    """Extract the first JSON array from *text*."""
    cleaned = _strip_markdown_fences(text)
    match = _JSON_ARRAY_RE.search(cleaned)
    if not match:
        raise ValueError("No JSON array found in input")
    return json.loads(match.group(1))


def _success(data: Any) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": json.dumps(data, default=str)}],
        "is_error": False,
    }


def _error(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "is_error": True,
    }


@tool(
    name="extract_personas",
    description=(
        "Parse and validate a persona-extraction JSON blob produced by "
        "Claude. Returns a list of validated persona objects in an MCP "
        "envelope, or is_error=True on malformed/invalid input."
    ),
    input_schema={"pdf_text": str},
)
async def extract_personas(args: dict[str, Any]) -> dict[str, Any]:
    """Parse persona JSON, validate against PersonaExtractionResult."""
    try:
        pdf_text = args.get("pdf_text", "")
        raw = _extract_json_object(pdf_text)
        result = PersonaExtractionResult.model_validate(raw)
        return _success(
            [p.model_dump(exclude_none=True) for p in result.key_figures]
        )
    except ValidationError as exc:
        logger.debug("extract_personas validation error: %s", exc)
        return _error(f"Validation error: {exc}")
    except (ValueError, json.JSONDecodeError) as exc:
        logger.debug("extract_personas JSON error: %s", exc)
        return _error(f"Invalid JSON: {exc}")


@tool(
    name="extract_scenes",
    description=(
        "Parse and validate a scene-extraction JSON array produced by "
        "Claude. Returns scenes sorted by sequence_order in an MCP "
        "envelope, or is_error=True on malformed/invalid input."
    ),
    input_schema={"pdf_text": str},
)
async def extract_scenes(args: dict[str, Any]) -> dict[str, Any]:
    """Parse scene JSON array, validate each against SceneSchema, sort."""
    try:
        pdf_text = args.get("pdf_text", "")
        raw_list = _extract_json_array(pdf_text)
        scenes = [SceneSchema.model_validate(item) for item in raw_list]
        scenes.sort(key=lambda s: s.sequence_order)
        return _success(
            [s.model_dump(exclude_none=True) for s in scenes]
        )
    except ValidationError as exc:
        logger.debug("extract_scenes validation error: %s", exc)
        return _error(f"Validation error: {exc}")
    except (ValueError, json.JSONDecodeError) as exc:
        logger.debug("extract_scenes JSON error: %s", exc)
        return _error(f"Invalid JSON: {exc}")


@tool(
    name="extract_objectives",
    description=(
        "Parse and validate a learning-objectives JSON array produced by "
        "Claude. Returns a list of objective strings in an MCP envelope, "
        "or is_error=True on malformed/invalid input."
    ),
    input_schema={"pdf_text": str},
)
async def extract_objectives(args: dict[str, Any]) -> dict[str, Any]:
    """Parse objectives JSON array, validate as list of non-empty strings."""
    try:
        pdf_text = args.get("pdf_text", "")
        raw_list = _extract_json_array(pdf_text)
        if not isinstance(raw_list, list):
            return _error("Expected a JSON array of strings")
        for i, item in enumerate(raw_list):
            if not isinstance(item, str):
                return _error(
                    f"Item at index {i} is {type(item).__name__}, expected str"
                )
        return _success(raw_list)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.debug("extract_objectives JSON error: %s", exc)
        return _error(f"Invalid JSON: {exc}")


__all__ = ["extract_personas", "extract_scenes", "extract_objectives"]
