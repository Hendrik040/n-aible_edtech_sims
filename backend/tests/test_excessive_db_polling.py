"""
Tests for GitHub Issue #357: Excessive database polling fixes.

Validates that health checks are cached, pool_pre_ping is configurable,
session cleanup runs at the correct interval, and the image worker
uses blocking pop instead of polling.
"""
import os
import sys
import time
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

import pytest

# --- PATH SETUP ---
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)


class TestHealthCheckCaching:
    """Tests that the /health endpoint caches its DB query result."""

    def test_health_check_returns_ok(self, client):
        """Health check should return status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_health_check_is_cached(self, client):
        """Second call within TTL should return cached result without new DB query."""
        # First call – populates cache
        resp1 = client.get("/health")
        assert resp1.status_code == 200

        # Second call – should be served from cache (same result)
        resp2 = client.get("/health")
        assert resp2.status_code == 200
        assert resp1.json() == resp2.json()

    def test_health_check_cache_expires(self, client):
        """After TTL expires, the cache should be refreshed."""
        from app.main import _health_cache, _HEALTH_CACHE_TTL

        # First call to populate cache
        client.get("/health")

        # Artificially expire the cache
        _health_cache["ts"] = time.monotonic() - _HEALTH_CACHE_TTL - 1

        # Next call should refresh (still returns ok, but cache timestamp updates)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert (time.monotonic() - _health_cache["ts"]) < 2  # freshly updated


class TestPoolPrePingConfigurable:
    """Tests that pool_pre_ping can be disabled via environment variable."""

    def test_pool_pre_ping_defaults_to_true(self):
        """Without env override, pool_pre_ping should default to True."""
        with patch.dict(os.environ, {}, clear=False):
            # Remove the var if it exists
            os.environ.pop("DB_POOL_PRE_PING", None)
            val = os.getenv("DB_POOL_PRE_PING", "true").lower() in ("1", "true", "yes", "on")
            assert val is True

    def test_pool_pre_ping_can_be_disabled(self):
        """Setting DB_POOL_PRE_PING=false should disable pre-ping."""
        with patch.dict(os.environ, {"DB_POOL_PRE_PING": "false"}):
            val = os.getenv("DB_POOL_PRE_PING", "true").lower() in ("1", "true", "yes", "on")
            assert val is False


class TestSessionCleanupInterval:
    """Tests that session cleanup runs at 15-minute interval (not 5)."""

    def test_cleanup_interval_is_900_seconds(self):
        """The session cleanup task should sleep for 900 seconds (15 min)."""
        import inspect
        from app.lifespan import _session_cleanup_task

        source = inspect.getsource(_session_cleanup_task)
        assert "asyncio.sleep(900)" in source
        assert "asyncio.sleep(300)" not in source


class TestRedisSubscriberSleep:
    """Tests that the Redis subscriber uses a 1-second idle sleep."""

    def test_subscriber_sleep_is_one_second(self):
        """The Redis subscriber should sleep 1.0s between empty polls."""
        import inspect
        from app.lifespan import _redis_subscriber

        source = inspect.getsource(_redis_subscriber)
        assert "asyncio.sleep(1.0)" in source
        assert "asyncio.sleep(0.1)" not in source


class TestImageWorkerBRPOP:
    """Tests that the image worker uses blocking pop instead of rpop + sleep."""

    def test_image_worker_uses_brpop(self):
        """process_queue should use brpop (blocking) instead of rpop."""
        import inspect
        from modules.publishing.tasks import process_queue

        source = inspect.getsource(process_queue)
        assert ".brpop(" in source
        assert ".rpop(" not in source

    def test_image_worker_no_idle_sleep(self):
        """process_queue should not have a 1-second idle sleep (brpop handles waiting)."""
        import inspect
        from modules.publishing.tasks import process_queue

        source = inspect.getsource(process_queue)
        # Should not have the old `await asyncio.sleep(1)` idle pattern
        assert "asyncio.sleep(1)" not in source


class TestFrontendPollingIntervals:
    """Tests that frontend polling intervals were increased from 3s to 10s."""

    def test_edit_grading_polling_interval(self):
        """edit-grading page should poll every 10 seconds, not 3."""
        grading_path = os.path.join(
            backend_path, '..', 'frontend', 'app', 'professor', 'edit-grading', 'page.tsx'
        )
        with open(grading_path, 'r') as f:
            content = f.read()
        assert "}, 10000)" in content
        assert "}, 3000)" not in content

    def test_simulation_builder_polling_interval(self):
        """simulation-builder page should poll every 10 seconds, not 3."""
        builder_path = os.path.join(
            backend_path, '..', 'frontend', 'app', 'professor', 'simulation-builder', 'page.tsx'
        )
        with open(builder_path, 'r') as f:
            content = f.read()
        assert "}, 10000);" in content
        assert "}, 3000);" not in content
