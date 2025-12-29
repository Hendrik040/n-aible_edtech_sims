# TTFB Optimization Plan: Chat Response Latency

> **Created:** December 25, 2024  
> **Status:** Implementation Ready  
> **Priority:** High  
> **Estimated Total Improvement:** 200-500ms reduction in TTFB

---

## Problem Statement

Users experience a **4+ second delay** (Time to First Byte) before seeing any chat response in the simulation. This creates a poor user experience even though the backend load tests show good performance (~245ms for chat messages).

### Current TTFB Breakdown (observed via DevTools)

| Phase | Time | Notes |
|-------|------|-------|
| Proxy overhead (Next.js) | ~100-200ms | Browser → Next.js → Backend |
| Auth + DB session | ~20-50ms | FastAPI dependencies |
| Load user_progress | ~50-100ms | DB query |
| Load orchestrator state | ~10-20ms | JSON parsing |
| **Load conversation history** | **~100-300ms** | ⚠️ DB query with LIKE filter |
| Create LangChain components | ~50-100ms | Memory, agent, executor |
| **OpenAI API call** | **~2000-4000ms** | ⚠️ Main bottleneck (future work) |
| **Total TTFB** | **~4000-5000ms** | Before first byte sent |

### What This Plan Addresses

- ✅ **Step B:** Database Index — Reduce conversation history query time
- ✅ **Step C:** Redis Cache — Eliminate repeated DB queries for conversation history
- 📝 **Future (A):** True OpenAI Streaming — Address the 2-4s OpenAI wait
- 📝 **Future (D):** Proxy Bypass — Reduce Next.js proxy overhead

---

## Step B: Database Index for Conversation Logs

### Problem

The `_load_conversation_history_from_db()` method in `persona_agent.py` runs this query:

```python
query = (
    session.query(ConversationLog)
    .filter(
        ConversationLog.user_progress_id == user_progress_id,
        ConversationLog.scene_id == scene_id,
        or_(
            ConversationLog.session_id == base_session_id,
            ConversationLog.session_id == self.persona_session_id,
            ConversationLog.session_id.like(f"{base_session_id}_%")  # ⚠️ LIKE query
        )
    )
    .order_by(ConversationLog.message_order.desc())
    .limit(max_messages)
)
```

Without an index, PostgreSQL performs a **full table scan** on `conversation_logs`.

### Solution

Create a composite index that covers the common query pattern.

### Implementation

#### Step B.1: Create Migration File

Create a new Alembic migration:

**File:** `backend/common/db/alembic/versions/XXXX_add_conversation_logs_index.py`

```python
"""Add index for conversation_logs lookup optimization

Revision ID: add_conv_logs_idx
Revises: [previous_revision]
Create Date: 2024-12-25

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'add_conv_logs_idx'
down_revision = '[REPLACE_WITH_LATEST_REVISION]'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Composite index for the most common query pattern
    # Covers: user_progress_id, scene_id, session_id filtering
    op.create_index(
        'idx_conversation_logs_progress_scene_session',
        'conversation_logs',
        ['user_progress_id', 'scene_id', 'session_id'],
        unique=False
    )
    
    # Index for message ordering (used in ORDER BY)
    op.create_index(
        'idx_conversation_logs_message_order',
        'conversation_logs',
        ['user_progress_id', 'message_order'],
        unique=False
    )
    
    # Partial index for session_id prefix matching (helps with LIKE queries)
    # Note: PostgreSQL can use btree indexes for prefix LIKE queries (e.g., 'abc%')
    op.create_index(
        'idx_conversation_logs_session_id',
        'conversation_logs',
        ['session_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_conversation_logs_session_id', table_name='conversation_logs')
    op.drop_index('idx_conversation_logs_message_order', table_name='conversation_logs')
    op.drop_index('idx_conversation_logs_progress_scene_session', table_name='conversation_logs')
```

#### Step B.2: Alternative - Direct SQL (Quick Test)

If you want to test immediately without a migration, run this in Neon Console:

```sql
-- Check existing indexes first
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'conversation_logs';

-- Create the indexes
CREATE INDEX CONCURRENTLY idx_conversation_logs_progress_scene_session 
ON conversation_logs(user_progress_id, scene_id, session_id);

CREATE INDEX CONCURRENTLY idx_conversation_logs_message_order 
ON conversation_logs(user_progress_id, message_order);

CREATE INDEX CONCURRENTLY idx_conversation_logs_session_id 
ON conversation_logs(session_id);

-- Analyze table to update query planner statistics
ANALYZE conversation_logs;
```

> **Note:** `CREATE INDEX CONCURRENTLY` doesn't lock the table during creation (safe for production).

#### Step B.3: Verify Index Usage

After creating indexes, verify they're being used:

```sql
EXPLAIN ANALYZE
SELECT * FROM conversation_logs 
WHERE user_progress_id = 1 
  AND scene_id = 1 
  AND (session_id = 'test' OR session_id LIKE 'test_%')
ORDER BY message_order DESC
LIMIT 20;
```

Look for `Index Scan` or `Index Only Scan` instead of `Seq Scan`.

### Expected Improvement

| Metric | Before | After |
|--------|--------|-------|
| Query time | 100-300ms | 5-20ms |
| TTFB reduction | — | ~100-280ms |

### Risks

- **None** — Adding indexes is safe and non-blocking with `CONCURRENTLY`
- Slight increase in write time (negligible for conversation logs)

---

## Step C: Redis Cache for Conversation History

### Problem

Every chat message triggers a database query to load conversation history:

```
Message 1 → Query DB for history → Process → Respond
Message 2 → Query DB for history → Process → Respond  (same history + 2 messages)
Message 3 → Query DB for history → Process → Respond  (same history + 4 messages)
...
```

This is wasteful because:
1. History changes incrementally (only new messages added)
2. Same user sends multiple messages in a session
3. DB round-trip adds latency on every message

### Solution

Cache conversation history in Redis with write-through pattern:
- **Read:** Check Redis first, fall back to DB
- **Write:** Append to Redis cache, batch persist to DB

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Message Flow                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Message arrives                                              │
│         │                                                        │
│         ▼                                                        │
│  2. Check Redis cache ──────────────────┐                       │
│         │                                │                       │
│    Cache HIT                        Cache MISS                   │
│         │                                │                       │
│         ▼                                ▼                       │
│  3a. Use cached history         3b. Query DB for history        │
│      (~5ms)                          (~100-300ms)                │
│         │                                │                       │
│         │                                ▼                       │
│         │                         Store in Redis                 │
│         │                                │                       │
│         └────────────┬───────────────────┘                       │
│                      ▼                                           │
│  4. Process message with LLM                                     │
│         │                                                        │
│         ▼                                                        │
│  5. Append new messages to Redis cache                           │
│     (user message + AI response)                                 │
│         │                                                        │
│         ▼                                                        │
│  6. Persist to DB (async/batched):                               │
│     - On scene change                                            │
│     - On simulation complete/submit                              │
│     - On 30 min inactivity (TTL expiry handler)                  │
│     - Every N messages (optional batching)                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Implementation

#### Step C.1: Create Conversation Cache Service

**File:** `backend/common/services/conversation_cache_service.py`

```python
"""
Conversation Cache Service.

Caches conversation history in Redis to reduce DB queries during chat.
Uses write-through caching with batched persistence to DB.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from common.services.cache_service import redis_manager
from common.db.models import ConversationLog

logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
CACHE_KEY_PREFIX = "conv_history"
MAX_CACHED_MESSAGES = 50  # Keep last 50 messages in cache


def _get_cache_key(user_progress_id: int, scene_id: int) -> str:
    """Generate Redis cache key for conversation history."""
    return f"{CACHE_KEY_PREFIX}:{user_progress_id}:{scene_id}"


def _serialize_message(log: ConversationLog) -> Dict[str, Any]:
    """Serialize a ConversationLog to dict for Redis storage."""
    return {
        "id": log.id,
        "user_progress_id": log.user_progress_id,
        "scene_id": log.scene_id,
        "session_id": log.session_id,
        "message_type": log.message_type,
        "sender_name": log.sender_name,
        "message_content": log.message_content,
        "message_order": log.message_order,
        "persona_id": log.persona_id,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _deserialize_message(data: Dict[str, Any]) -> Dict[str, Any]:
    """Deserialize a message dict from Redis.
    
    Returns dict with same structure as ConversationLog attributes.
    Note: This is a dict, not an ORM object, to avoid DB session issues.
    """
    return {
        "id": data.get("id"),
        "user_progress_id": data.get("user_progress_id"),
        "scene_id": data.get("scene_id"),
        "session_id": data.get("session_id"),
        "message_type": data.get("message_type"),
        "sender_name": data.get("sender_name"),
        "message_content": data.get("message_content"),
        "message_order": data.get("message_order"),
        "persona_id": data.get("persona_id"),
        "created_at": data.get("created_at"),
    }


class ConversationCacheService:
    """Service for caching conversation history in Redis."""
    
    @staticmethod
    def get_cached_history(
        user_progress_id: int,
        scene_id: int,
        session_id_filter: Optional[str] = None
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Get conversation history from Redis cache.
        
        Args:
            user_progress_id: User progress ID
            scene_id: Scene ID
            session_id_filter: Optional session_id prefix to filter by
            
        Returns:
            List of message dicts if cache hit, None if cache miss
        """
        cache_key = _get_cache_key(user_progress_id, scene_id)
        
        try:
            cached_data = redis_manager.get(cache_key)
            if cached_data is None:
                logger.debug(f"[CONV_CACHE] Cache MISS for {cache_key}")
                return None
            
            # Parse cached JSON
            if isinstance(cached_data, str):
                messages = json.loads(cached_data)
            else:
                messages = cached_data
            
            # Filter by session_id if provided
            if session_id_filter:
                base_session_id = session_id_filter
                if "_persona_" in session_id_filter:
                    base_session_id = session_id_filter.rsplit("_persona_", 1)[0]
                
                messages = [
                    msg for msg in messages
                    if (msg.get("session_id") == base_session_id or
                        msg.get("session_id") == session_id_filter or
                        (msg.get("session_id") or "").startswith(f"{base_session_id}_"))
                ]
            
            logger.debug(
                f"[CONV_CACHE] Cache HIT for {cache_key}: {len(messages)} messages"
            )
            return messages
            
        except Exception as e:
            logger.warning(f"[CONV_CACHE] Error reading cache: {e}")
            return None
    
    @staticmethod
    def set_cached_history(
        user_progress_id: int,
        scene_id: int,
        messages: List[ConversationLog]
    ) -> bool:
        """
        Store conversation history in Redis cache.
        
        Args:
            user_progress_id: User progress ID
            scene_id: Scene ID
            messages: List of ConversationLog objects to cache
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = _get_cache_key(user_progress_id, scene_id)
        
        try:
            # Serialize messages
            serialized = [_serialize_message(msg) for msg in messages]
            
            # Keep only last N messages
            if len(serialized) > MAX_CACHED_MESSAGES:
                serialized = serialized[-MAX_CACHED_MESSAGES:]
            
            # Store in Redis with TTL
            redis_manager.set(
                cache_key,
                json.dumps(serialized),
                ttl=CACHE_TTL_SECONDS
            )
            
            logger.debug(
                f"[CONV_CACHE] Cached {len(serialized)} messages for {cache_key}"
            )
            return True
            
        except Exception as e:
            logger.warning(f"[CONV_CACHE] Error writing cache: {e}")
            return False
    
    @staticmethod
    def append_message(
        user_progress_id: int,
        scene_id: int,
        message_data: Dict[str, Any]
    ) -> bool:
        """
        Append a new message to the cached history.
        
        Args:
            user_progress_id: User progress ID
            scene_id: Scene ID
            message_data: Message dict to append
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = _get_cache_key(user_progress_id, scene_id)
        
        try:
            # Get existing cache
            cached_data = redis_manager.get(cache_key)
            
            if cached_data is None:
                # No cache exists - just store the single message
                messages = [message_data]
            else:
                # Parse and append
                if isinstance(cached_data, str):
                    messages = json.loads(cached_data)
                else:
                    messages = cached_data
                messages.append(message_data)
                
                # Trim to max size
                if len(messages) > MAX_CACHED_MESSAGES:
                    messages = messages[-MAX_CACHED_MESSAGES:]
            
            # Store back
            redis_manager.set(
                cache_key,
                json.dumps(messages),
                ttl=CACHE_TTL_SECONDS
            )
            
            logger.debug(
                f"[CONV_CACHE] Appended message to {cache_key}, "
                f"total: {len(messages)} messages"
            )
            return True
            
        except Exception as e:
            logger.warning(f"[CONV_CACHE] Error appending to cache: {e}")
            return False
    
    @staticmethod
    def invalidate_cache(user_progress_id: int, scene_id: int) -> bool:
        """
        Invalidate (delete) cached conversation history.
        
        Call this when:
        - Scene changes
        - Simulation resets
        - User logs out
        
        Args:
            user_progress_id: User progress ID
            scene_id: Scene ID
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = _get_cache_key(user_progress_id, scene_id)
        
        try:
            redis_manager.delete(cache_key)
            logger.debug(f"[CONV_CACHE] Invalidated cache for {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"[CONV_CACHE] Error invalidating cache: {e}")
            return False
    
    @staticmethod
    def refresh_ttl(user_progress_id: int, scene_id: int) -> bool:
        """
        Refresh the TTL on cached conversation history.
        
        Call this on each message to keep active conversations cached.
        
        Args:
            user_progress_id: User progress ID
            scene_id: Scene ID
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = _get_cache_key(user_progress_id, scene_id)
        
        try:
            # Get current value
            cached_data = redis_manager.get(cache_key)
            if cached_data is not None:
                # Re-set with fresh TTL
                redis_manager.set(cache_key, cached_data, ttl=CACHE_TTL_SECONDS)
                return True
            return False
        except Exception as e:
            logger.warning(f"[CONV_CACHE] Error refreshing TTL: {e}")
            return False


# Singleton instance
conversation_cache = ConversationCacheService()
```

#### Step C.2: Update PersonaAgent to Use Cache

**File:** `backend/modules/simulation/agents/persona_agent.py`

Modify `_load_conversation_history_from_db()` to check cache first:

```python
# Add import at top of file
from common.services.conversation_cache_service import conversation_cache

# Replace _load_conversation_history_from_db method:

def _load_conversation_history_from_db(
    self,
    user_progress_id: int,
    scene_id: int,
    current_message: str = None,
    db: Optional[Session] = None,
) -> List[ConversationLog]:
    """Load conversation history with Redis cache optimization.
    
    First checks Redis cache, falls back to DB on cache miss.
    Caches DB results for subsequent requests.
    """
    try:
        # Step 1: Check Redis cache first
        cached_messages = conversation_cache.get_cached_history(
            user_progress_id=user_progress_id,
            scene_id=scene_id,
            session_id_filter=self.persona_session_id
        )
        
        if cached_messages is not None:
            # Cache hit - convert to mock ConversationLog-like objects
            # Filter out current message if provided
            if current_message:
                cached_messages = [
                    msg for msg in cached_messages
                    if not (msg.get("message_type") == "user" and 
                            msg.get("message_content") == current_message)
                ]
            
            logger.info(
                f"[CONV_CACHE] Using cached history: {len(cached_messages)} messages "
                f"for persona {self.persona.name}, user_progress_id={user_progress_id}"
            )
            
            # Return as list of dicts (chat() method will handle this)
            return cached_messages
        
        # Step 2: Cache miss - query database
        logger.info(
            f"[CONV_CACHE] Cache miss, querying DB for persona {self.persona.name}, "
            f"user_progress_id={user_progress_id}, scene_id={scene_id}"
        )
        
        # ... [KEEP EXISTING DB QUERY CODE HERE] ...
        # The existing query code from lines 446-531
        
        # Step 3: Cache the results for next time
        if conversation_logs:
            conversation_cache.set_cached_history(
                user_progress_id=user_progress_id,
                scene_id=scene_id,
                messages=conversation_logs
            )
        
        return conversation_logs
        
    except Exception as e:
        logger.error(f"Error loading conversation history: {e}", exc_info=True)
        raise
```

#### Step C.3: Update Chat Handler to Append to Cache

**File:** `backend/modules/simulation/handlers/chat_handler.py`

After saving a message to DB, also append to cache:

```python
# Add import at top
from common.services.conversation_cache_service import conversation_cache

# After each create_conversation_log() call, add cache append:

# Example - after saving user message (around line 177):
self.repository.create_conversation_log(
    user_progress_id=user_progress.id,
    scene_id=correct_scene_id,
    message_type="user",
    sender_name="User",
    message_content=message,
    message_order=next_order,
    session_id=user_message_session_id
)
self.db.commit()

# ADD THIS: Append to cache
conversation_cache.append_message(
    user_progress_id=user_progress.id,
    scene_id=correct_scene_id,
    message_data={
        "message_type": "user",
        "sender_name": "User",
        "message_content": message,
        "message_order": next_order,
        "session_id": user_message_session_id,
        "persona_id": None,
    }
)
```

#### Step C.4: Invalidate Cache on Scene Change

**File:** `backend/modules/simulation/core/scene_progression.py`

Add cache invalidation when scene changes:

```python
from common.services.conversation_cache_service import conversation_cache

# In progress_to_next_scene method, after scene transition:
conversation_cache.invalidate_cache(
    user_progress_id=user_progress.id,
    scene_id=current_scene_id  # Old scene
)
```

### Expected Improvement

| Metric | Before | After |
|--------|--------|-------|
| First message | 100-300ms (DB query) | 100-300ms (DB query, then cached) |
| Subsequent messages | 100-300ms (DB query) | 5-10ms (Redis cache) |
| Average per session | ~200ms | ~20ms |
| TTFB reduction | — | ~100-280ms for messages 2+ |

### Risks

- **Low Risk:** Redis is already used in the app (cache_service.py exists)
- **Mitigation:** Cache miss falls back to DB, so no data loss
- **TTL ensures cleanup:** Inactive conversations auto-expire after 30 min

---

## Future Improvements (Notes)

### Future A: True OpenAI Streaming

**Problem:** `AgentExecutor.ainvoke()` waits for full response before streaming.

**Solution:** Use `ChatOpenAI(streaming=True)` with callbacks to stream tokens as they arrive from OpenAI.

**Complexity:** Medium-High — Requires refactoring persona_agent.py to not use AgentExecutor, or using streaming-compatible agent patterns.

**Expected Impact:** ~2-3 second TTFB reduction (the biggest win).

**When to implement:** After B+C are done and we want further optimization.

---

### Future D: Bypass Proxy for Chat Endpoints

**Problem:** Browser → Next.js proxy → Backend adds ~100-200ms.

**Solution:** Configure CORS to allow direct browser → backend calls for SSE endpoints.

**Changes needed:**
1. Backend: Add CORS headers for production frontend domains
2. Backend: Ensure cookies work cross-origin (`SameSite=None; Secure`)
3. Frontend: Call backend directly for `/api/simulation/linear-chat-stream`

**Expected Impact:** ~50-150ms TTFB reduction.

**When to implement:** After B+C, if further optimization needed.

---

## Implementation Checklist

### Step B: Database Index
- [ ] Check existing indexes on `conversation_logs` table
- [ ] Create Alembic migration (or run SQL directly)
- [ ] Run migration on dev/staging
- [ ] Verify index usage with `EXPLAIN ANALYZE`
- [ ] Deploy to production
- [ ] Monitor query times in logs

### Step C: Redis Cache
- [ ] Create `conversation_cache_service.py`
- [ ] Update `persona_agent.py` to use cache
- [ ] Update `chat_handler.py` to append to cache
- [ ] Add cache invalidation on scene change
- [ ] Test locally with multiple messages
- [ ] Deploy to staging and test
- [ ] Deploy to production
- [ ] Monitor cache hit/miss ratio in logs

### Verification
- [ ] Measure TTFB before changes (baseline)
- [ ] Measure TTFB after Step B
- [ ] Measure TTFB after Step C
- [ ] Document improvements

---

## Metrics to Track

After implementation, monitor these in Railway logs:

```
[CONV_CACHE] Cache HIT for conv_history:123:5: 15 messages
[CONV_CACHE] Cache MISS, querying DB...
[CONV_CACHE] Cached 15 messages for conv_history:123:5
```

And in DevTools:
- TTFB for `linear-chat-stream` requests
- Compare first message vs. subsequent messages in same session


