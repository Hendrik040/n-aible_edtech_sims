"""Unit tests for the async ``EmbeddingsService`` wrapper."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import RateLimitError

from common.services.embeddings_service import (
    EmbeddingsService,
    MalformedEmbeddingResponseError,
)


def _make_rate_limit_error(message: str = "rate limited") -> RateLimitError:
    """Build a realistic ``RateLimitError`` with a fake 429 response."""
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(429, request=request)
    return RateLimitError(message=message, response=response, body=None)


def _make_embedding_response(vectors: list[list[float]]) -> MagicMock:
    """Build a mock embeddings.create response with the given vectors."""
    response = MagicMock()
    response.data = [MagicMock(embedding=vec) for vec in vectors]
    return response


@pytest.fixture
def mock_client() -> MagicMock:
    """An ``AsyncOpenAI``-shaped mock whose ``embeddings.create`` is an ``AsyncMock``."""
    client = MagicMock()
    client.embeddings = MagicMock()
    client.embeddings.create = AsyncMock()
    return client


@pytest.fixture
def service(mock_client: MagicMock) -> EmbeddingsService:
    return EmbeddingsService(client=mock_client)


@pytest.mark.asyncio
async def test_embed_happy_path(service: EmbeddingsService, mock_client: MagicMock) -> None:
    vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    mock_client.embeddings.create.return_value = _make_embedding_response(vectors)

    result = await service.embed(["hello", "world"])

    assert result == vectors
    mock_client.embeddings.create.assert_called_once()
    kwargs = mock_client.embeddings.create.call_args.kwargs
    assert kwargs["input"] == ["hello", "world"]
    assert kwargs["model"] == "text-embedding-3-small"


@pytest.mark.asyncio
async def test_embed_empty_input_short_circuits(
    service: EmbeddingsService, mock_client: MagicMock
) -> None:
    result = await service.embed([])

    assert result == []
    mock_client.embeddings.create.assert_not_called()


@pytest.mark.asyncio
async def test_embed_retries_on_rate_limit(
    service: EmbeddingsService, mock_client: MagicMock
) -> None:
    rate_err = _make_rate_limit_error()
    success = _make_embedding_response([[0.1, 0.2]])
    mock_client.embeddings.create.side_effect = [rate_err, rate_err, success]

    with patch(
        "common.services.embeddings_service.asyncio.sleep",
        new_callable=AsyncMock,
    ) as sleep_mock:
        result = await service.embed(["hello"])

    assert result == [[0.1, 0.2]]
    assert mock_client.embeddings.create.call_count == 3
    sleep_args = [call.args[0] for call in sleep_mock.call_args_list]
    assert sleep_args == [1, 2]


@pytest.mark.asyncio
async def test_embed_reraises_when_all_attempts_rate_limited(
    service: EmbeddingsService, mock_client: MagicMock
) -> None:
    mock_client.embeddings.create.side_effect = _make_rate_limit_error()

    with patch(
        "common.services.embeddings_service.asyncio.sleep",
        new_callable=AsyncMock,
    ):
        with pytest.raises(RateLimitError):
            await service.embed(["hello"])

    assert mock_client.embeddings.create.call_count == 3


@pytest.mark.asyncio
async def test_embed_does_not_retry_on_other_errors(
    service: EmbeddingsService, mock_client: MagicMock
) -> None:
    """Non-rate-limit errors must propagate immediately without retry."""
    mock_client.embeddings.create.side_effect = RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await service.embed(["hello"])

    mock_client.embeddings.create.assert_called_once()


def _malformed_cases() -> list[tuple[str, int, Any, str]]:
    """Return (case_id, input_count, mock_response, expected_message_fragment)."""
    missing_data = MagicMock(spec=[])  # no ``data`` attribute

    count_mismatch = MagicMock()
    count_mismatch.data = [MagicMock(embedding=[0.1])]  # 1 item, 2 inputs

    item_without_embedding = MagicMock()
    bare = MagicMock(spec=[])  # no ``embedding`` attribute
    item_without_embedding.data = [bare]

    embedding_not_list = MagicMock()
    embedding_not_list.data = [MagicMock(embedding="not-a-list")]

    return [
        ("missing_data", 1, missing_data, "data"),
        ("count_mismatch", 2, count_mismatch, "2"),
        ("item_missing_embedding", 1, item_without_embedding, "embedding"),
        ("embedding_not_list", 1, embedding_not_list, "embedding"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case_id,input_count,mock_response,expected_match",
    _malformed_cases(),
    ids=[case[0] for case in _malformed_cases()],
)
async def test_embed_raises_on_malformed_response(
    service: EmbeddingsService,
    mock_client: MagicMock,
    case_id: str,
    input_count: int,
    mock_response: Any,
    expected_match: str,
) -> None:
    mock_client.embeddings.create.return_value = mock_response
    inputs = [f"text-{i}" for i in range(input_count)]

    with pytest.raises(MalformedEmbeddingResponseError, match=expected_match):
        await service.embed(inputs)
