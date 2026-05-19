"""
Tests for OpenAI error handling and retry logic.

Covers:
- Error classification (rate limit, auth, transient, invalid request, internal)
- User-facing message sanitization (no implementation details leaked)
- Retry logic with exponential backoff
- Retry-After header respect for rate limiting
- Stream retry (only before first token)
- Non-retryable errors fail immediately
"""

import asyncio
import pytest
from unittest.mock import MagicMock, patch

import openai
from httpx import Response, Request

from common.services.openai_error_handler import (
    ErrorCategory,
    classify_openai_error,
    get_user_message,
    is_retryable,
    with_retries,
    stream_with_retries,
    _get_retry_delay,
    USER_MESSAGES,
    MAX_RETRIES,
    BASE_DELAY_SECONDS,
)


# --- Helpers to create OpenAI error instances ---

def _make_request():
    return Request("POST", "https://api.openai.com/v1/chat/completions")


def _make_response(status_code: int, body: str = '{"error": {"message": "test"}}'):
    return Response(status_code=status_code, request=_make_request(), text=body)


def _rate_limit_error(retry_after: str = None):
    resp = _make_response(429)
    if retry_after:
        resp.headers["retry-after"] = retry_after
    return openai.RateLimitError(
        message="Rate limit exceeded",
        response=resp,
        body={"error": {"message": "Rate limit exceeded"}},
    )


def _auth_error():
    return openai.AuthenticationError(
        message="Invalid API key",
        response=_make_response(401),
        body={"error": {"message": "Invalid API key"}},
    )


def _api_status_error(status_code: int):
    return openai.APIStatusError(
        message=f"Error {status_code}",
        response=_make_response(status_code),
        body={"error": {"message": f"Error {status_code}"}},
    )


def _connection_error():
    return openai.APIConnectionError(request=_make_request())


def _generic_api_error():
    return openai.APIError(
        message="Unknown API error",
        request=_make_request(),
        body=None,
    )


# === Error Classification Tests ===


class TestClassifyOpenaiError:
    """Error classification correctly maps OpenAI exceptions to categories."""

    def test_rate_limit_error(self):
        assert classify_openai_error(_rate_limit_error()) == ErrorCategory.RATE_LIMITED

    def test_auth_error(self):
        assert classify_openai_error(_auth_error()) == ErrorCategory.AUTH_ERROR

    def test_connection_error(self):
        assert classify_openai_error(_connection_error()) == ErrorCategory.TRANSIENT

    def test_502_gateway_error(self):
        assert classify_openai_error(_api_status_error(502)) == ErrorCategory.TRANSIENT

    def test_503_service_unavailable(self):
        assert classify_openai_error(_api_status_error(503)) == ErrorCategory.TRANSIENT

    def test_504_gateway_timeout(self):
        assert classify_openai_error(_api_status_error(504)) == ErrorCategory.TRANSIENT

    def test_429_via_status_error(self):
        assert classify_openai_error(_api_status_error(429)) == ErrorCategory.RATE_LIMITED

    def test_401_via_status_error(self):
        assert classify_openai_error(_api_status_error(401)) == ErrorCategory.AUTH_ERROR

    def test_400_bad_request(self):
        assert classify_openai_error(_api_status_error(400)) == ErrorCategory.INVALID_REQUEST

    def test_generic_api_error(self):
        assert classify_openai_error(_generic_api_error()) == ErrorCategory.TRANSIENT

    def test_non_openai_error(self):
        assert classify_openai_error(ValueError("oops")) == ErrorCategory.INTERNAL


# === Retryable Tests ===


class TestIsRetryable:
    def test_rate_limited_is_retryable(self):
        assert is_retryable(ErrorCategory.RATE_LIMITED) is True

    def test_transient_is_retryable(self):
        assert is_retryable(ErrorCategory.TRANSIENT) is True

    def test_auth_error_not_retryable(self):
        assert is_retryable(ErrorCategory.AUTH_ERROR) is False

    def test_invalid_request_not_retryable(self):
        assert is_retryable(ErrorCategory.INVALID_REQUEST) is False

    def test_internal_not_retryable(self):
        assert is_retryable(ErrorCategory.INTERNAL) is False


# === User Message Tests ===


class TestGetUserMessage:
    """User-facing messages should not leak implementation details."""

    def test_rate_limit_message(self):
        msg = get_user_message(_rate_limit_error())
        assert msg == USER_MESSAGES[ErrorCategory.RATE_LIMITED]
        assert "api" not in msg.lower() or "ai service" in msg.lower()
        assert "openai" not in msg.lower()

    def test_auth_error_message(self):
        msg = get_user_message(_auth_error())
        assert msg == USER_MESSAGES[ErrorCategory.AUTH_ERROR]
        assert "api key" not in msg.lower()
        assert "openai" not in msg.lower()

    def test_transient_error_message(self):
        msg = get_user_message(_connection_error())
        assert msg == USER_MESSAGES[ErrorCategory.TRANSIENT]
        assert "openai" not in msg.lower()

    def test_invalid_request_message(self):
        msg = get_user_message(_api_status_error(400))
        assert msg == USER_MESSAGES[ErrorCategory.INVALID_REQUEST]

    def test_internal_error_message(self):
        msg = get_user_message(ValueError("internal details"))
        assert msg == USER_MESSAGES[ErrorCategory.INTERNAL]
        assert "internal details" not in msg


# === Retry Delay Tests ===


class TestGetRetryDelay:
    def test_exponential_backoff(self):
        err = _connection_error()
        d0 = _get_retry_delay(err, 0)
        d1 = _get_retry_delay(err, 1)
        d2 = _get_retry_delay(err, 2)
        assert d0 == BASE_DELAY_SECONDS * 1
        assert d1 == BASE_DELAY_SECONDS * 2
        assert d2 == BASE_DELAY_SECONDS * 4

    def test_max_delay_cap(self):
        err = _connection_error()
        d = _get_retry_delay(err, 100, max_delay=10.0)
        assert d == 10.0

    def test_retry_after_header(self):
        err = _rate_limit_error(retry_after="5")
        d = _get_retry_delay(err, 0)
        assert d == 5.0

    def test_retry_after_capped_by_max_delay(self):
        err = _rate_limit_error(retry_after="999")
        d = _get_retry_delay(err, 0, max_delay=30.0)
        assert d == 30.0

    def test_retry_after_header_on_generic_429_status_error(self):
        """A 429 APIStatusError (not RateLimitError) should also honor Retry-After."""
        resp = _make_response(429)
        resp.headers["retry-after"] = "7"
        err = openai.APIStatusError(
            message="Rate limited",
            response=resp,
            body={"error": {"message": "Rate limited"}},
        )
        d = _get_retry_delay(err, 0)
        assert d == 7.0


# === with_retries Tests ===


class TestWithRetries:
    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        call_count = 0

        async def succeed():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await with_retries(succeed, max_retries=3, context="test")
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_transient_then_succeeds(self):
        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise _connection_error()
            return "ok"

        async def instant_sleep(delay):
            pass

        with patch("common.services.openai_error_handler.asyncio.sleep", side_effect=instant_sleep):
            result = await with_retries(fail_then_succeed, max_retries=3, context="test")
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_non_retryable_fails_immediately(self):
        call_count = 0

        async def auth_fail():
            nonlocal call_count
            call_count += 1
            raise _auth_error()

        with pytest.raises(openai.AuthenticationError):
            await with_retries(auth_fail, max_retries=3, context="test")
        assert call_count == 1  # No retries for auth errors

    @pytest.mark.asyncio
    async def test_exhausted_retries_raises(self):
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise _connection_error()

        async def instant_sleep(delay):
            pass

        with patch("common.services.openai_error_handler.asyncio.sleep", side_effect=instant_sleep):
            with pytest.raises(openai.APIConnectionError):
                await with_retries(always_fail, max_retries=2, context="test")
        assert call_count == 3  # Initial + 2 retries


# === stream_with_retries Tests ===


class TestStreamWithRetries:
    @pytest.mark.asyncio
    async def test_stream_success(self):
        async def gen():
            yield "a"
            yield "b"
            yield "c"

        tokens = []
        async for token in stream_with_retries(gen, max_retries=3, context="test"):
            tokens.append(token)
        assert tokens == ["a", "b", "c"]

    @pytest.mark.asyncio
    async def test_stream_retries_before_first_token(self):
        call_count = 0

        async def fail_then_stream():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise _connection_error()
            yield "token1"
            yield "token2"

        async def instant_sleep(delay):
            pass

        tokens = []
        with patch("common.services.openai_error_handler.asyncio.sleep", side_effect=instant_sleep):
            async for token in stream_with_retries(fail_then_stream, max_retries=3, context="test"):
                tokens.append(token)
        assert tokens == ["token1", "token2"]
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_stream_no_retry_after_first_token(self):
        """If error occurs after tokens were yielded, don't retry (data already sent)."""
        call_count = 0

        async def fail_mid_stream():
            nonlocal call_count
            call_count += 1
            yield "token1"
            raise _connection_error()

        tokens = []
        with pytest.raises(openai.APIConnectionError):
            async for token in stream_with_retries(fail_mid_stream, max_retries=3, context="test"):
                tokens.append(token)
        assert tokens == ["token1"]
        assert call_count == 1  # No retry

    @pytest.mark.asyncio
    async def test_stream_non_retryable_fails_immediately(self):
        call_count = 0

        async def auth_fail_stream():
            nonlocal call_count
            call_count += 1
            raise _auth_error()
            yield  # Make it a generator

        with pytest.raises(openai.AuthenticationError):
            async for _ in stream_with_retries(auth_fail_stream, max_retries=3, context="test"):
                pass
        assert call_count == 1
