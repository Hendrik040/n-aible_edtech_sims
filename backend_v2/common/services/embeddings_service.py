"""Async wrapper around ``openai.AsyncOpenAI`` for generating embeddings.

Public surface:

    service = EmbeddingsService(client=AsyncOpenAI())
    vectors = await service.embed(["hello", "world"])

The wrapper is intentionally minimal: no caching, no batching, no LangChain.
The OpenAI client is injected via the constructor so tests can substitute a
mock.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any

from openai import AsyncOpenAI, RateLimitError


_DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
_MAX_ATTEMPTS = 3


class MalformedEmbeddingResponseError(Exception):
    """Raised when the OpenAI embeddings response does not match the expected shape."""


def _resolve_model() -> str:
    """Resolve the embedding model name.

    Reads ``EMBEDDING_MODEL`` from the environment (which is how
    ``common/config.py`` is populated) and falls back to
    ``text-embedding-3-small`` if unset.
    """
    return os.environ.get("EMBEDDING_MODEL") or _DEFAULT_EMBEDDING_MODEL


class EmbeddingsService:
    """Thin async wrapper around the OpenAI embeddings endpoint."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return an embedding vector for each input string.

        - Empty input short-circuits to ``[]`` without hitting the API.
        - Retries up to 3 times on ``openai.RateLimitError`` with
          exponential backoff (1s, 2s between attempts).
        - Raises :class:`MalformedEmbeddingResponseError` if the response
          shape does not match the inputs.
        """
        if not texts:
            return []

        model = _resolve_model()
        response = await self._create_with_retry(model=model, texts=texts)
        return _parse_response(response, expected=len(texts))

    async def _create_with_retry(self, *, model: str, texts: list[str]) -> Any:
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return await self._client.embeddings.create(
                    model=model, input=texts
                )
            except RateLimitError:
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
        raise RuntimeError("unreachable: retry loop exited without returning")  # pragma: no cover


def _parse_response(response: Any, *, expected: int) -> list[list[float]]:
    data = getattr(response, "data", None)
    if data is None:
        raise MalformedEmbeddingResponseError(
            "OpenAI embeddings response is missing the 'data' field"
        )
    if len(data) != expected:
        raise MalformedEmbeddingResponseError(
            f"expected {expected} embeddings in response, got {len(data)}"
        )
    vectors: list[list[float]] = []
    for index, item in enumerate(data):
        embedding = getattr(item, "embedding", None)
        if not isinstance(embedding, list):
            raise MalformedEmbeddingResponseError(
                f"embedding at index {index} is missing or not a list"
            )
        vectors.append(embedding)
    return vectors
