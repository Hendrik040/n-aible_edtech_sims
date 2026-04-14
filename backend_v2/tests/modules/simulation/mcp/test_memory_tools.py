"""Unit tests for the ``recall_memory`` MCP tool (phase-2.1).

Every external collaborator (embeddings service, pgvector store, repository)
is replaced with an in-memory fake. The only thing under test is the tool's
envelope contract, filtering, hybrid ranking, and error handling.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.simulation.mcp import memory_tools
from modules.simulation.mcp.memory_tools import recall_memory


def _row(
    *,
    persona_id: int | str,
    scene_id: int | str,
    content: str,
    similarity: float,
    importance: float | str | None = None,
    content_key: str = "content",
) -> dict[str, Any]:
    """Build a ``pgvector_store.similarity_search`` result row."""
    metadata: dict[str, Any] = {
        "persona_id": str(persona_id),
        "scene_id": str(scene_id),
        content_key: content,
    }
    if importance is not None:
        metadata["importance_score"] = importance
    return {
        "id": 1,
        "entity_type": "memory",
        "entity_id": content,
        "embedding_metadata": metadata,
        "similarity_score": similarity,
    }


@pytest.fixture
def mock_validator():
    """Patch ``repository.validate_persona_in_scene`` with a ``MagicMock``."""
    with patch.object(
        memory_tools.repository, "validate_persona_in_scene", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def mock_embeddings():
    """Patch the embeddings singleton factory with an ``AsyncMock``-backed service."""
    service = MagicMock()
    service.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    with patch.object(
        memory_tools, "_get_embeddings_service", return_value=service
    ):
        yield service


@pytest.fixture
def mock_similarity_search():
    """Patch ``pgvector_store.similarity_search`` with an ``AsyncMock``."""
    async_mock = AsyncMock()
    with patch.object(
        memory_tools.pgvector_store, "similarity_search", async_mock
    ):
        yield async_mock


@pytest.fixture
def sample_rows() -> list[dict[str, Any]]:
    """Five persona+scene-matched rows ordered by descending similarity."""
    return [
        _row(persona_id=1, scene_id=10, content=f"memory-{i}", similarity=0.9 - i * 0.1)
        for i in range(5)
    ]


@pytest.mark.asyncio
async def test_recall_memory_returns_topk_chunks(
    mock_validator, mock_embeddings, mock_similarity_search, sample_rows
) -> None:
    mock_similarity_search.return_value = sample_rows

    result = await recall_memory.handler(
        {"persona_id": 1, "scene_id": 10, "query": "budget overruns", "k": 5}
    )

    assert result["is_error"] is False
    assert [block["text"] for block in result["content"]] == [
        f"memory-{i}" for i in range(5)
    ]
    assert all(block["type"] == "text" for block in result["content"])

    mock_validator.assert_called_once_with(1, 10)
    mock_embeddings.embed.assert_awaited_once_with(["budget overruns"])
    mock_similarity_search.assert_awaited_once()
    call_args = mock_similarity_search.await_args
    assert call_args.args[0] == [0.1, 0.2, 0.3]
    assert call_args.args[1] == "memory"
    # Over-fetch to allow hybrid re-ranking; callers still get at most k blocks.
    assert call_args.kwargs["k"] >= 5
    # Persona / scene scoping is pushed into the SQL query, not filtered
    # client-side, so the store sees the filter as a metadata constraint.
    assert call_args.kwargs["metadata_filter"] == {
        "persona_id": 1,
        "scene_id": 10,
    }


@pytest.mark.asyncio
async def test_recall_memory_respects_k_param(
    mock_validator, mock_embeddings, mock_similarity_search, sample_rows
) -> None:
    mock_similarity_search.return_value = sample_rows

    result = await recall_memory.handler(
        {"persona_id": 1, "scene_id": 10, "query": "risk", "k": 3}
    )

    assert result["is_error"] is False
    assert len(result["content"]) == 3
    assert [block["text"] for block in result["content"]] == [
        "memory-0",
        "memory-1",
        "memory-2",
    ]


@pytest.mark.asyncio
async def test_recall_memory_default_k_is_five(
    mock_validator, mock_embeddings, mock_similarity_search, sample_rows
) -> None:
    # When ``k`` is omitted the tool should default to 5.
    mock_similarity_search.return_value = sample_rows

    result = await recall_memory.handler(
        {"persona_id": 1, "scene_id": 10, "query": "anything"}
    )

    assert result["is_error"] is False
    assert len(result["content"]) == 5


@pytest.mark.asyncio
async def test_recall_memory_empty_query_returns_empty(
    mock_validator, mock_embeddings, mock_similarity_search
) -> None:
    for query in ("", "   ", "\n\t"):
        result = await recall_memory.handler(
            {"persona_id": 1, "scene_id": 10, "query": query, "k": 5}
        )
        assert result == {"content": [], "is_error": False}

    # No DB / embedding calls for an empty query.
    mock_validator.assert_not_called()
    mock_embeddings.embed.assert_not_called()
    mock_similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_recall_memory_missing_persona_returns_error_envelope(
    mock_embeddings, mock_similarity_search
) -> None:
    with patch.object(
        memory_tools.repository,
        "validate_persona_in_scene",
        return_value=False,
    ):
        result = await recall_memory.handler(
            {"persona_id": 999, "scene_id": 10, "query": "risk", "k": 5}
        )

    assert result["is_error"] is True
    assert result["content"] == [
        {"type": "text", "text": "Persona not found or not in scene"}
    ]
    # A missing persona short-circuits before we hit embeddings / pgvector.
    mock_embeddings.embed.assert_not_called()
    mock_similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_recall_memory_pushes_persona_scene_filter_to_vector_store(
    mock_validator, mock_embeddings, mock_similarity_search
) -> None:
    """The tool delegates persona / scene scoping to the vector store.

    Since filtering happens in SQL, the ranker trusts every row it receives.
    We verify (a) the filter is forwarded to ``similarity_search`` and
    (b) every row the mock returns is surfaced (no client-side discard) —
    this is the behaviour that guarantees ``k`` scoped matches return fully.
    """
    mock_similarity_search.return_value = [
        _row(persona_id=1, scene_id=10, content="hit-1", similarity=0.9),
        _row(persona_id=1, scene_id=10, content="hit-2", similarity=0.7),
    ]

    result = await recall_memory.handler(
        {"persona_id": 7, "scene_id": 42, "query": "q", "k": 5}
    )

    call_args = mock_similarity_search.await_args
    assert call_args.kwargs["metadata_filter"] == {
        "persona_id": 7,
        "scene_id": 42,
    }
    texts = [block["text"] for block in result["content"]]
    assert texts == ["hit-1", "hit-2"]


@pytest.mark.asyncio
async def test_recall_memory_uses_constant_overfetch_no_retry_loop(
    mock_validator, mock_embeddings, mock_similarity_search, sample_rows
) -> None:
    """SQL-side filtering makes the adaptive fetch loop unnecessary.

    Because the store already scopes by persona / scene, one fetch at
    ``k * _OVERFETCH_MULTIPLIER`` is enough to feed the hybrid re-ranker.
    """
    from modules.simulation.mcp.memory_tools import _OVERFETCH_MULTIPLIER

    mock_similarity_search.return_value = sample_rows[:2]  # fewer than k

    result = await recall_memory.handler(
        {"persona_id": 1, "scene_id": 10, "query": "q", "k": 5}
    )

    # Only one fetch — no widening retry when matches are scarce, since the
    # SQL filter has already returned every in-scope candidate.
    assert mock_similarity_search.await_count == 1
    call_args = mock_similarity_search.await_args
    assert call_args.kwargs["k"] == 5 * _OVERFETCH_MULTIPLIER
    assert result["is_error"] is False
    assert len(result["content"]) == 2


@pytest.mark.asyncio
async def test_recall_memory_hybrid_score_reranks_on_importance(
    mock_validator, mock_embeddings, mock_similarity_search
) -> None:
    # High importance lifts a low-similarity row above a higher-similarity row.
    mock_similarity_search.return_value = [
        _row(persona_id=1, scene_id=10, content="high-sim-low-imp",
             similarity=0.9, importance=0.0),
        _row(persona_id=1, scene_id=10, content="low-sim-high-imp",
             similarity=0.5, importance=1.0),
    ]

    result = await recall_memory.handler(
        {"persona_id": 1, "scene_id": 10, "query": "q", "k": 2}
    )

    # 0.5 * 0.7 + 1.0 * 0.3 = 0.65  >  0.9 * 0.7 + 0.0 * 0.3 = 0.63
    assert [block["text"] for block in result["content"]] == [
        "low-sim-high-imp",
        "high-sim-low-imp",
    ]


@pytest.mark.asyncio
async def test_recall_memory_handles_malformed_metadata(
    mock_validator, mock_embeddings, mock_similarity_search
) -> None:
    mock_similarity_search.return_value = [
        # Not a dict → skipped.
        {"id": 1, "embedding_metadata": "not-a-dict", "similarity_score": 0.9},
        # Missing embedding_metadata → skipped.
        {"id": 2, "similarity_score": 0.85},
        # Missing content fields → skipped.
        {
            "id": 3,
            "embedding_metadata": {"persona_id": "1", "scene_id": "10"},
            "similarity_score": 0.8,
        },
        # Non-numeric importance → fallback to 0.0, still returned.
        _row(
            persona_id=1,
            scene_id=10,
            content="kept",
            similarity=0.5,
            importance="not-a-number",
        ),
        # Non-numeric similarity → fallback to 0.0, still returned.
        {
            "id": 4,
            "embedding_metadata": {
                "persona_id": "1",
                "scene_id": "10",
                "content": "also-kept",
            },
            "similarity_score": "bogus",
        },
        # memory_content fallback key is accepted.
        _row(
            persona_id=1,
            scene_id=10,
            content="legacy-key",
            similarity=0.4,
            content_key="memory_content",
        ),
    ]

    result = await recall_memory.handler(
        {"persona_id": 1, "scene_id": 10, "query": "q", "k": 5}
    )

    texts = {block["text"] for block in result["content"]}
    assert texts == {"kept", "also-kept", "legacy-key"}
    assert result["is_error"] is False


@pytest.mark.asyncio
async def test_recall_memory_non_positive_k_returns_empty(
    mock_validator, mock_embeddings, mock_similarity_search
) -> None:
    for k in (0, -1):
        result = await recall_memory.handler(
            {"persona_id": 1, "scene_id": 10, "query": "q", "k": k}
        )
        assert result == {"content": [], "is_error": False}

    mock_validator.assert_not_called()
    mock_embeddings.embed.assert_not_called()
    mock_similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_recall_memory_embeddings_exception_returns_error_envelope(
    mock_validator, mock_similarity_search
) -> None:
    service = MagicMock()
    service.embed = AsyncMock(side_effect=RuntimeError("openai down"))
    with patch.object(
        memory_tools, "_get_embeddings_service", return_value=service
    ):
        result = await recall_memory.handler(
            {"persona_id": 1, "scene_id": 10, "query": "q", "k": 5}
        )

    assert result == {
        "content": [{"type": "text", "text": "Failed to recall memory"}],
        "is_error": True,
    }
    mock_similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_recall_memory_similarity_search_exception_returns_error_envelope(
    mock_validator, mock_embeddings
) -> None:
    async_mock = AsyncMock(side_effect=RuntimeError("pgvector exploded"))
    with patch.object(
        memory_tools.pgvector_store, "similarity_search", async_mock
    ):
        result = await recall_memory.handler(
            {"persona_id": 1, "scene_id": 10, "query": "q", "k": 5}
        )

    assert result["is_error"] is True
    assert result["content"] == [
        {"type": "text", "text": "Failed to recall memory"}
    ]


@pytest.mark.asyncio
async def test_recall_memory_empty_embedding_returns_empty(
    mock_validator, mock_similarity_search
) -> None:
    service = MagicMock()
    service.embed = AsyncMock(return_value=[])
    with patch.object(
        memory_tools, "_get_embeddings_service", return_value=service
    ):
        result = await recall_memory.handler(
            {"persona_id": 1, "scene_id": 10, "query": "q", "k": 5}
        )

    assert result == {"content": [], "is_error": False}
    mock_similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_recall_memory_missing_required_field_returns_error_envelope(
    mock_embeddings, mock_similarity_search
) -> None:
    result = await recall_memory.handler({"scene_id": 10, "query": "q", "k": 5})

    assert result == {
        "content": [{"type": "text", "text": "Failed to recall memory"}],
        "is_error": True,
    }


def test_get_embeddings_service_is_cached() -> None:
    # Reset the cached instance so we exercise the lazy-construction branch.
    memory_tools._embeddings_service_singleton = None
    try:
        with patch.object(memory_tools, "AsyncOpenAI") as openai_cls:
            openai_cls.return_value = MagicMock()
            first = memory_tools._get_embeddings_service()
            second = memory_tools._get_embeddings_service()
        assert first is second
        openai_cls.assert_called_once()
    finally:
        memory_tools._embeddings_service_singleton = None
