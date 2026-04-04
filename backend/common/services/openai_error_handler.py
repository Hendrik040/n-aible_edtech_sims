"""
OpenAI API Error Handling and Retry Logic

Provides structured error handling for OpenAI API calls with:
- Exponential backoff retry for transient failures (502, 429, connection errors)
- Retry-After header respect for rate limiting
- Error classification (retryable vs fatal)
- Sanitized user-facing error messages
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Optional, TypeVar

import openai

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration
MAX_RETRIES = 3
BASE_DELAY_SECONDS = 1.0
MAX_DELAY_SECONDS = 30.0


class ErrorCategory(str, Enum):
    """Classification of OpenAI API errors for frontend consumption."""
    RATE_LIMITED = "rate_limited"
    AUTH_ERROR = "auth_error"
    TRANSIENT = "transient"
    INVALID_REQUEST = "invalid_request"
    INTERNAL = "internal"


# User-facing messages per error category (no implementation details leaked)
USER_MESSAGES = {
    ErrorCategory.RATE_LIMITED: (
        "The AI service is currently experiencing high demand. "
        "Please wait a moment and try again."
    ),
    ErrorCategory.AUTH_ERROR: (
        "There is a configuration issue with the AI service. "
        "Please contact your instructor or administrator."
    ),
    ErrorCategory.TRANSIENT: (
        "The AI service encountered a temporary issue. "
        "Please try sending your message again."
    ),
    ErrorCategory.INVALID_REQUEST: (
        "There was an issue processing your message. "
        "Please try rephrasing or shortening your message."
    ),
    ErrorCategory.INTERNAL: (
        "I'm sorry, I'm having trouble processing that right now. "
        "Please try again."
    ),
}


def classify_openai_error(error: Exception) -> ErrorCategory:
    """Classify an exception into an error category."""
    if isinstance(error, openai.RateLimitError):
        return ErrorCategory.RATE_LIMITED
    if isinstance(error, openai.AuthenticationError):
        return ErrorCategory.AUTH_ERROR
    if isinstance(error, openai.APIConnectionError):
        return ErrorCategory.TRANSIENT
    if isinstance(error, openai.APIStatusError):
        status = getattr(error, "status_code", 0)
        if status in (502, 503, 504):
            return ErrorCategory.TRANSIENT
        if status == 429:
            return ErrorCategory.RATE_LIMITED
        if status == 401:
            return ErrorCategory.AUTH_ERROR
        if 400 <= status < 500:
            return ErrorCategory.INVALID_REQUEST
        return ErrorCategory.TRANSIENT
    if isinstance(error, openai.APIError):
        return ErrorCategory.TRANSIENT
    return ErrorCategory.INTERNAL


def is_retryable(category: ErrorCategory) -> bool:
    """Whether an error category should be retried."""
    return category in (ErrorCategory.RATE_LIMITED, ErrorCategory.TRANSIENT)


def get_user_message(error: Exception) -> str:
    """Get a safe, user-facing error message for an exception."""
    category = classify_openai_error(error)
    return USER_MESSAGES[category]


def _get_retry_delay(
    error: Exception,
    attempt: int,
    base_delay: float = BASE_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
) -> float:
    """Calculate retry delay with exponential backoff and Retry-After support."""
    # Respect Retry-After header from rate limit responses
    if isinstance(error, openai.RateLimitError):
        response = getattr(error, "response", None)
        if response is not None:
            headers = getattr(response, "headers", {})
            if hasattr(headers, "get"):
                ra_value = headers.get("retry-after")
                if ra_value is not None:
                    try:
                        return min(float(ra_value), max_delay)
                    except (ValueError, TypeError):
                        pass

    # Exponential backoff: base * 2^attempt
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)


async def with_retries(
    func: Callable[..., Any],
    *args: Any,
    max_retries: int = MAX_RETRIES,
    context: str = "OpenAI API call",
    **kwargs: Any,
) -> Any:
    """Execute an async function with retry logic for transient OpenAI errors.

    Args:
        func: Async callable to execute.
        *args: Positional arguments for func.
        max_retries: Maximum number of retry attempts.
        context: Description for log messages.
        **kwargs: Keyword arguments for func.

    Returns:
        The result of func.

    Raises:
        The original exception if all retries are exhausted or error is not retryable.
    """
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except (openai.APIError, openai.APIConnectionError) as e:
            last_error = e
            category = classify_openai_error(e)

            if not is_retryable(category) or attempt >= max_retries:
                logger.error(
                    "[OPENAI_RETRY] %s failed (attempt %d/%d, category=%s): %s",
                    context, attempt + 1, max_retries + 1, category.value, e,
                )
                raise

            delay = _get_retry_delay(e, attempt)
            logger.warning(
                "[OPENAI_RETRY] %s transient error (attempt %d/%d, category=%s), "
                "retrying in %.1fs: %s",
                context, attempt + 1, max_retries + 1, category.value, delay, e,
            )
            await asyncio.sleep(delay)

    # Should not reach here, but just in case
    if last_error:
        raise last_error


async def stream_with_retries(
    func: Callable[..., AsyncGenerator[str, None]],
    *args: Any,
    max_retries: int = MAX_RETRIES,
    context: str = "OpenAI streaming call",
    **kwargs: Any,
) -> AsyncGenerator[str, None]:
    """Execute an async generator with retry logic.

    Only retries if the error occurs before any tokens are yielded.
    Once streaming has started, errors are not retried (partial response already sent).

    Args:
        func: Async generator callable.
        *args: Positional arguments for func.
        max_retries: Maximum number of retry attempts.
        context: Description for log messages.
        **kwargs: Keyword arguments for func.

    Yields:
        String tokens from the async generator.
    """
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        tokens_yielded = False
        try:
            async for token in func(*args, **kwargs):
                tokens_yielded = True
                yield token
            return  # Completed successfully
        except (openai.APIError, openai.APIConnectionError) as e:
            last_error = e
            category = classify_openai_error(e)

            # Don't retry if we already started streaming or error is not retryable
            if tokens_yielded or not is_retryable(category) or attempt >= max_retries:
                if tokens_yielded:
                    logger.error(
                        "[OPENAI_RETRY] %s failed mid-stream (attempt %d/%d): %s",
                        context, attempt + 1, max_retries + 1, e,
                    )
                else:
                    logger.error(
                        "[OPENAI_RETRY] %s failed (attempt %d/%d, category=%s): %s",
                        context, attempt + 1, max_retries + 1, category.value, e,
                    )
                raise

            delay = _get_retry_delay(e, attempt)
            logger.warning(
                "[OPENAI_RETRY] %s transient error before first token "
                "(attempt %d/%d, category=%s), retrying in %.1fs: %s",
                context, attempt + 1, max_retries + 1, category.value, delay, e,
            )
            await asyncio.sleep(delay)

    if last_error:
        raise last_error
