"""Unit tests for the ``lookup_rubric`` MCP tool (phase-2.2).

Every external collaborator (embeddings service, pgvector store, scenario
material-id loader) is replaced with an in-memory fake. The only thing
under test is the tool's envelope contract, scenario scoping, top-k
ordering, and error-envelope behaviour on unknown scenarios.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.simulation.mcp import grading_tools
from modules.simulation.mcp.grading_tools import lookup_rubric


def _row(
    *,
    material_id: int,
    chunk_index: int,
    content: str,
    similarity: float,
) -> dict[str, Any]:
    """Build a ``pgvector_store.similarity_search`` result row for grading."""
    return {
        "id": material_id * 100 + chunk_index,
        "material_id": material_id,
        "chunk_index": chunk_index,
        "content": content,
        "content_hash": f"hash-{material_id}-{chunk_index}",
        "similarity_score": similarity,
    }


@pytest.fixture
def mock_material_ids():
    """Patch ``_load_scenario_material_ids`` with a ``MagicMock``."""
    with patch.object(
        grading_tools, "_load_scenario_material_ids"
    ) as mock:
        yield mock


@pytest.fixture
def mock_embeddings():
    """Patch the embeddings singleton factory with a mock service."""
    service = MagicMock()
    service.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    with patch.object(
        grading_tools, "_get_embeddings_service", return_value=service
    ):
        yield service


@pytest.fixture
def mock_similarity_search():
    """Patch ``pgvector_store.similarity_search`` with an ``AsyncMock``."""
    async_mock = AsyncMock()
    with patch.object(
        grading_tools.pgvector_store, "similarity_search", async_mock
    ):
        yield async_mock


@pytest.mark.asyncio
async def test_lookup_rubric_returns_topk(
    mock_material_ids, mock_embeddings, mock_similarity_search
) -> None:
    """More than ``k`` candidates → the top ``k`` by similarity are returned."""
    mock_material_ids.return_value = {1, 2}
    # Five chunks belonging to the scenario's materials, interleaved similarity.
    mock_similarity_search.return_value = [
        _row(material_id=1, chunk_index=0, content="rubric-A", similarity=0.95),
        _row(material_id=2, chunk_index=0, content="rubric-B", similarity=0.80),
        _row(material_id=1, chunk_index=1, content="rubric-C", similarity=0.70),
        _row(material_id=2, chunk_index=1, content="rubric-D", similarity=0.60),
        _row(material_id=1, chunk_index=2, content="rubric-E", similarity=0.50),
    ]

    result = await lookup_rubric.handler(
        {"scenario_id": 42, "query": "evaluate analysis quality", "k": 3}
    )

    assert result["is_error"] is False
    assert result["content"] == [
        {"type": "text", "text": "rubric-A"},
        {"type": "text", "text": "rubric-B"},
        {"type": "text", "text": "rubric-C"},
    ]
    structured = result["structuredContent"]["results"]
    assert len(structured) == 3
    assert [item["content"] for item in structured] == [
        "rubric-A",
        "rubric-B",
        "rubric-C",
    ]
    # Ordered by relevance_score, descending.
    scores = [item["relevance_score"] for item in structured]
    assert scores == sorted(scores, reverse=True)
    assert structured[0]["material_id"] == 1
    assert structured[0]["chunk_index"] == 0
    assert structured[0]["relevance_score"] == pytest.approx(0.95)

    mock_material_ids.assert_called_once_with(42)
    mock_embeddings.embed.assert_awaited_once_with(["evaluate analysis quality"])
    mock_similarity_search.assert_awaited()
    call_args = mock_similarity_search.await_args
    assert call_args.args[0] == [0.1, 0.2, 0.3]
    assert call_args.args[1] == "grading"
    # Over-fetch to allow scenario filtering; callers still get at most k blocks.
    assert call_args.kwargs["k"] >= 3


@pytest.mark.asyncio
async def test_lookup_rubric_default_k_is_three(
    mock_material_ids, mock_embeddings, mock_similarity_search
) -> None:
    """Omitted ``k`` defaults to 3."""
    mock_material_ids.return_value = {1}
    mock_similarity_search.return_value = [
        _row(material_id=1, chunk_index=i, content=f"chunk-{i}", similarity=0.9 - i * 0.1)
        for i in range(5)
    ]

    result = await lookup_rubric.handler(
        {"scenario_id": 7, "query": "anything"}
    )

    assert result["is_error"] is False
    assert len(result["content"]) == 3
    assert len(result["structuredContent"]["results"]) == 3


@pytest.mark.asyncio
async def test_lookup_rubric_scoped_to_scenario(
    mock_material_ids, mock_embeddings, mock_similarity_search
) -> None:
    """Chunks whose ``material_id`` is not owned by the scenario are filtered out."""
    # Scenario 42 owns materials {1, 2}. Candidates include material 99 from
    # another scenario — it must NOT appear in the result.
    mock_material_ids.return_value = {1, 2}
    mock_similarity_search.return_value = [
        _row(material_id=99, chunk_index=0, content="other-scenario-1",
             similarity=0.99),
        _row(material_id=1, chunk_index=0, content="keep-A", similarity=0.90),
        _row(material_id=99, chunk_index=1, content="other-scenario-2",
             similarity=0.85),
        _row(material_id=2, chunk_index=0, content="keep-B", similarity=0.80),
        _row(material_id=1, chunk_index=1, content="keep-C", similarity=0.70),
    ]

    result = await lookup_rubric.handler(
        {"scenario_id": 42, "query": "q", "k": 5}
    )

    assert result["is_error"] is False
    texts = [block["text"] for block in result["content"]]
    assert texts == ["keep-A", "keep-B", "keep-C"]
    # No cross-contamination from scenario 99.
    assert all("other-scenario" not in text for text in texts)
    structured_material_ids = {
        item["material_id"] for item in result["structuredContent"]["results"]
    }
    assert structured_material_ids <= {1, 2}


@pytest.mark.asyncio
async def test_lookup_rubric_unknown_scenario_returns_error_envelope(
    mock_embeddings, mock_similarity_search
) -> None:
    """A scenario with no completed grading materials → error envelope."""
    with patch.object(
        grading_tools, "_load_scenario_material_ids", return_value=set()
    ):
        result = await lookup_rubric.handler(
            {"scenario_id": 999, "query": "q", "k": 3}
        )

    assert result["is_error"] is True
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    # Error message mentions the scenario_id that was not found.
    assert "999" in result["content"][0]["text"]
    # A missing scenario short-circuits before we hit embeddings / pgvector.
    mock_embeddings.embed.assert_not_called()
    mock_similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_rubric_empty_query_returns_empty(
    mock_material_ids, mock_embeddings, mock_similarity_search
) -> None:
    """Empty / whitespace query short-circuits without DB work."""
    for query in ("", "   ", "\n\t"):
        result = await lookup_rubric.handler(
            {"scenario_id": 1, "query": query, "k": 3}
        )
        assert result == {
            "content": [],
            "structuredContent": {"results": []},
            "is_error": False,
        }

    mock_material_ids.assert_not_called()
    mock_embeddings.embed.assert_not_called()
    mock_similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_rubric_non_positive_k_returns_empty(
    mock_material_ids, mock_embeddings, mock_similarity_search
) -> None:
    """``k <= 0`` short-circuits without DB work."""
    for k in (0, -1):
        result = await lookup_rubric.handler(
            {"scenario_id": 1, "query": "q", "k": k}
        )
        assert result == {
            "content": [],
            "structuredContent": {"results": []},
            "is_error": False,
        }

    mock_material_ids.assert_not_called()
    mock_embeddings.embed.assert_not_called()
    mock_similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_rubric_empty_embedding_returns_empty(
    mock_material_ids, mock_similarity_search
) -> None:
    """An embedding service that returns an empty vector → empty success."""
    mock_material_ids.return_value = {1}
    service = MagicMock()
    service.embed = AsyncMock(return_value=[])
    with patch.object(
        grading_tools, "_get_embeddings_service", return_value=service
    ):
        result = await lookup_rubric.handler(
            {"scenario_id": 1, "query": "q", "k": 3}
        )

    assert result == {
        "content": [],
        "structuredContent": {"results": []},
        "is_error": False,
    }
    mock_similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_rubric_similarity_search_exception_returns_error_envelope(
    mock_material_ids, mock_embeddings
) -> None:
    """Unexpected exceptions from pgvector surface as a generic error envelope."""
    mock_material_ids.return_value = {1}
    async_mock = AsyncMock(side_effect=RuntimeError("pgvector exploded"))
    with patch.object(
        grading_tools.pgvector_store, "similarity_search", async_mock
    ):
        result = await lookup_rubric.handler(
            {"scenario_id": 1, "query": "q", "k": 3}
        )

    assert result["is_error"] is True
    assert result["content"] == [
        {"type": "text", "text": "Failed to look up rubric"}
    ]


@pytest.mark.asyncio
async def test_lookup_rubric_missing_required_field_returns_error_envelope(
    mock_embeddings, mock_similarity_search
) -> None:
    """A missing ``scenario_id`` key falls through to the generic error envelope."""
    result = await lookup_rubric.handler({"query": "q", "k": 3})

    assert result == {
        "content": [{"type": "text", "text": "Failed to look up rubric"}],
        "is_error": True,
    }


@pytest.mark.asyncio
async def test_lookup_rubric_non_numeric_similarity_falls_back_to_zero(
    mock_material_ids, mock_embeddings, mock_similarity_search
) -> None:
    """Malformed similarity scores default to 0.0 without crashing."""
    mock_material_ids.return_value = {1}
    mock_similarity_search.return_value = [
        {
            "material_id": 1,
            "chunk_index": 0,
            "content": "good",
            "similarity_score": "not-a-number",
        },
    ]

    result = await lookup_rubric.handler(
        {"scenario_id": 1, "query": "q", "k": 3}
    )

    assert result["is_error"] is False
    assert result["structuredContent"]["results"][0]["relevance_score"] == 0.0


@pytest.mark.asyncio
async def test_lookup_rubric_overfetches_when_scenario_hits_are_sparse(
    mock_material_ids, mock_embeddings
) -> None:
    """If the first fetch under-serves, the tool over-fetches until k are found."""
    mock_material_ids.return_value = {1}

    # First batch contains mostly foreign chunks; second batch has the hits.
    batch_first = [
        _row(material_id=99, chunk_index=i, content=f"foreign-{i}",
             similarity=0.9 - i * 0.01)
        for i in range(9)
    ]
    batch_second = batch_first + [
        _row(material_id=1, chunk_index=0, content="hit-A", similarity=0.50),
        _row(material_id=1, chunk_index=1, content="hit-B", similarity=0.40),
        _row(material_id=1, chunk_index=2, content="hit-C", similarity=0.30),
    ]

    async def side_effect(_vec, _ns, k: int):
        return batch_second if k > 9 else batch_first

    async_mock = AsyncMock(side_effect=side_effect)
    with patch.object(
        grading_tools.pgvector_store, "similarity_search", async_mock
    ):
        result = await lookup_rubric.handler(
            {"scenario_id": 1, "query": "q", "k": 3}
        )

    assert result["is_error"] is False
    texts = [block["text"] for block in result["content"]]
    assert texts == ["hit-A", "hit-B", "hit-C"]
    # Over-fetch triggered at least one extra round-trip.
    assert async_mock.await_count >= 2


def test_get_embeddings_service_is_cached() -> None:
    """The embeddings singleton is constructed lazily and reused."""
    grading_tools._embeddings_service_singleton = None
    try:
        with patch.object(grading_tools, "AsyncOpenAI") as openai_cls:
            openai_cls.return_value = MagicMock()
            first = grading_tools._get_embeddings_service()
            second = grading_tools._get_embeddings_service()
        assert first is second
        openai_cls.assert_called_once()
    finally:
        grading_tools._embeddings_service_singleton = None
