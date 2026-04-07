"""
Tests for ConversationCacheService atomic Redis list operations.

Verifies that conversation caching uses atomic RPUSH/LTRIM instead of
the old non-atomic GET→modify→SET pattern (fixes race condition in #236).
"""
import json
from unittest.mock import MagicMock, patch, call
import pytest

from common.services.conversation_cache_service import (
    ConversationCacheService,
    CachedMessage,
    _dict_to_cached_message,
    _get_cache_key,
    CACHE_TTL_SECONDS,
    MAX_CACHED_MESSAGES,
)


def _make_message(order: int, sender: str = "student", session_id: str = "sess1") -> dict:
    """Helper to create a message dict."""
    return {
        "id": order,
        "user_progress_id": 1,
        "scene_id": 1,
        "session_id": session_id,
        "message_type": "user" if sender == "student" else "ai",
        "sender_name": sender,
        "message_content": f"Message {order}",
        "message_order": order,
        "persona_id": None,
        "created_at": "2026-01-01T00:00:00",
    }


class _FakeORM:
    """Minimal stand-in for a ConversationLog ORM object."""
    def __init__(self, data: dict):
        for k, v in data.items():
            setattr(self, k, v)
        # created_at needs .isoformat()
        if isinstance(self.created_at, str):
            self.created_at = type("dt", (), {"isoformat": lambda self_: data["created_at"]})()


# ── append_message ────────────────────────────────────────────────────


@patch("common.services.conversation_cache_service.redis_manager")
class TestAppendMessage:

    def test_append_uses_rpush_not_get_set(self, mock_rm):
        """append_message must use atomic RPUSH, not GET→SET."""
        mock_rm.rpush.return_value = 1
        mock_rm.ltrim.return_value = True
        mock_rm.llen.return_value = 1
        mock_rm.redis = MagicMock()

        msg = _make_message(1)
        result = ConversationCacheService.append_message(1, 1, msg)

        assert result is True
        # RPUSH called with JSON-serialized message
        mock_rm.rpush.assert_called_once()
        pushed_json = mock_rm.rpush.call_args[0][1]
        assert json.loads(pushed_json) == msg

        # LTRIM called to enforce max size
        mock_rm.ltrim.assert_called_once_with(
            _get_cache_key(1, 1), -MAX_CACHED_MESSAGES, -1
        )

        # TTL refreshed
        mock_rm.redis.expire.assert_called_once_with(
            _get_cache_key(1, 1), CACHE_TTL_SECONDS
        )

        # Old GET/SET pattern must NOT be used
        mock_rm.get.assert_not_called()
        mock_rm.set.assert_not_called()

    def test_append_returns_false_on_error(self, mock_rm):
        """append_message returns False when RPUSH raises."""
        mock_rm.rpush.side_effect = Exception("connection lost")

        result = ConversationCacheService.append_message(1, 1, _make_message(1))
        assert result is False


# ── set_cached_history ────────────────────────────────────────────────


@patch("common.services.conversation_cache_service.redis_manager")
class TestSetCachedHistory:

    def test_stores_as_list_elements(self, mock_rm):
        """set_cached_history must delete old key, then RPUSH individual items."""
        mock_rm.delete.return_value = True
        mock_rm.rpush.return_value = 3
        mock_rm.redis = MagicMock()

        msgs = [_FakeORM(_make_message(i)) for i in range(3)]
        result = ConversationCacheService.set_cached_history(1, 1, msgs)

        assert result is True
        mock_rm.delete.assert_called_once_with(_get_cache_key(1, 1))
        mock_rm.rpush.assert_called_once()

        # Verify each pushed item is a JSON string
        pushed_args = mock_rm.rpush.call_args[0]
        assert pushed_args[0] == _get_cache_key(1, 1)
        for item in pushed_args[1:]:
            parsed = json.loads(item)
            assert "message_content" in parsed

        # TTL set
        mock_rm.redis.expire.assert_called_once()

        # Old SET pattern must NOT be used
        mock_rm.set.assert_not_called()

    def test_trims_to_max_cached_messages(self, mock_rm):
        """When more than MAX_CACHED_MESSAGES, only the last N are stored."""
        mock_rm.delete.return_value = True
        mock_rm.rpush.return_value = MAX_CACHED_MESSAGES
        mock_rm.redis = MagicMock()

        msgs = [_FakeORM(_make_message(i)) for i in range(MAX_CACHED_MESSAGES + 10)]
        ConversationCacheService.set_cached_history(1, 1, msgs)

        pushed_args = mock_rm.rpush.call_args[0]
        # key + MAX_CACHED_MESSAGES items
        assert len(pushed_args) == 1 + MAX_CACHED_MESSAGES

    def test_empty_list_does_not_rpush(self, mock_rm):
        """set_cached_history with empty messages should not RPUSH."""
        mock_rm.delete.return_value = True
        mock_rm.redis = MagicMock()

        ConversationCacheService.set_cached_history(1, 1, [])
        mock_rm.rpush.assert_not_called()


# ── get_cached_history ────────────────────────────────────────────────


@patch("common.services.conversation_cache_service.redis_manager")
class TestGetCachedHistory:

    def test_reads_from_lrange(self, mock_rm):
        """get_cached_history must use lrange, not get."""
        messages = [_make_message(i) for i in range(3)]
        # lrange returns already-parsed dicts (RedisManager auto-parses JSON)
        mock_rm.lrange.return_value = messages

        result = ConversationCacheService.get_cached_history(1, 1)

        mock_rm.lrange.assert_called_once_with(_get_cache_key(1, 1), 0, -1)
        mock_rm.get.assert_not_called()

        assert result is not None
        assert len(result) == 3
        assert all(isinstance(m, CachedMessage) for m in result)
        assert result[0].message_content == "Message 0"

    def test_empty_list_returns_none(self, mock_rm):
        """Empty Redis list = cache miss → return None."""
        mock_rm.lrange.return_value = []

        result = ConversationCacheService.get_cached_history(1, 1)
        assert result is None

    def test_session_id_filtering(self, mock_rm):
        """Session ID filtering still works with list storage."""
        messages = [
            _make_message(0, session_id="sess1"),
            _make_message(1, session_id="sess2"),
            _make_message(2, session_id="sess1_persona_X"),
        ]
        mock_rm.lrange.return_value = messages

        result = ConversationCacheService.get_cached_history(1, 1, session_id_filter="sess1")

        assert result is not None
        assert len(result) == 2  # sess1 and sess1_persona_X
        assert result[0].session_id == "sess1"
        assert result[1].session_id == "sess1_persona_X"


# ── Race condition regression ─────────────────────────────────────────


@patch("common.services.conversation_cache_service.redis_manager")
class TestRaceConditionRegression:

    def test_concurrent_appends_are_safe(self, mock_rm):
        """Two concurrent append_message calls should each independently RPUSH.

        With the old GET→SET pattern, concurrent calls could overwrite each other.
        With RPUSH, each call atomically appends without reading first.
        """
        mock_rm.rpush.return_value = 1
        mock_rm.ltrim.return_value = True
        mock_rm.llen.return_value = 2
        mock_rm.redis = MagicMock()

        msg_a = _make_message(1, sender="student")
        msg_b = _make_message(2, sender="AI Persona")

        ConversationCacheService.append_message(1, 1, msg_a)
        ConversationCacheService.append_message(1, 1, msg_b)

        # Two independent RPUSHes — neither reads existing state
        assert mock_rm.rpush.call_count == 2
        assert mock_rm.get.call_count == 0  # no GET at all
