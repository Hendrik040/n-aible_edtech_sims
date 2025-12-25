# Worker-Specific In-Progress Tracking Implementation Plan

## Context & Decision

**Issue:** CodeRabbit flagged a critical bug in `tasks.py:202-221` that breaks multi-replica deployments.

**Decision:** Implement worker-specific Redis keys using Railway's `RAILWAY_REPLICA_ID`.

**Target:** Support 100+ concurrent users with 2-3 replicas (scalable to more).

---

## Problem Summary

In multi-replica deployments (e.g., `numReplicas = 2` on Railway), each worker replica runs `process_simulation_queue()` independently. On startup, the current code at `tasks.py:202-221` **deletes the entire shared** `IN_PROGRESS_SET`, which removes in-progress markers from OTHER workers that are still actively processing jobs.

**Scenario with 8 replicas:**
```
Replica 0 restarts → deletes IN_PROGRESS_SET → 
  Replicas 1-7 lose their job tracking → 
    should_use_queue() returns wrong values →
      Potential duplicate processing or routing failures
```

This breaks:
- `get_in_progress_count()` returning incorrect (lower) counts
- `should_use_queue()` routing logic making wrong decisions
- Potential duplicate job processing or lost job tracking

---

## Solution: Worker-Specific Redis Keys

Each worker gets its own in-progress set keyed by a unique `WORKER_ID`. On startup, each worker only cleans up its own stale entries.

**Key pattern:** `simulation:in_progress:{RAILWAY_REPLICA_ID}`

**Why `RAILWAY_REPLICA_ID`?**
- Railway automatically provides this for each replica ([docs](https://docs.railway.com/guides/optimize-performance#replica-id-environment-variable))
- Deterministic: Replica 0 always gets `0`, Replica 1 gets `1`, etc.
- No manual configuration needed
- Perfect for logging and debugging

---

## Implementation Steps

### Step 1: Add WORKER_ID to Configuration

**File:** `backend/common/config.py`

Add the following import at the top of the file:

```python
import uuid
```

Then add this property to the `Settings` class (around line 40-50):

```python
@property
def worker_id(self) -> str:
    """
    Get unique worker ID for this instance.
    
    Railway automatically provides RAILWAY_REPLICA_ID for each replica.
    See: https://docs.railway.com/guides/optimize-performance#replica-id-environment-variable
    
    Priority: RAILWAY_REPLICA_ID > HOSTNAME > generated UUID (fallback for local dev)
    """
    import os
    worker_id = (
        os.getenv("RAILWAY_REPLICA_ID") or
        os.getenv("HOSTNAME") or
        f"local-{uuid.uuid4().hex[:8]}"
    )
    return worker_id
```

**Note:** `RAILWAY_REPLICA_ID` is the primary identifier. The fallbacks are only for:
- Local development (no Railway env)
- Edge cases where the env var isn't set

---

### Step 2: Update simulation_queue_service.py

**File:** `backend/common/services/simulation_queue_service.py`

#### 2a. Change the IN_PROGRESS_SET to be worker-specific

Replace line 28:
```python
# OLD:
IN_PROGRESS_SET = "simulation:in_progress"
```

With:
```python
# NEW: Worker-specific in-progress tracking
# Each Railway replica gets its own set via RAILWAY_REPLICA_ID
from common.config import get_settings

_settings = get_settings()
WORKER_ID = _settings.worker_id  # e.g., "0", "1", "2" from Railway, or "local-xxx" for dev
IN_PROGRESS_SET = f"simulation:in_progress:{WORKER_ID}"

# Pattern for finding all worker in-progress sets (used for aggregation)
IN_PROGRESS_PATTERN = "simulation:in_progress:*"
```

#### 2b. Update get_in_progress_count() to count ALL workers

Replace the function at lines 488-490:
```python
# OLD:
def get_in_progress_count() -> int:
    """Get the number of jobs currently in progress."""
    return redis_manager.scard(IN_PROGRESS_SET)
```

With:
```python
# NEW:
def get_in_progress_count() -> int:
    """
    Get the total number of jobs currently in progress across ALL workers.
    
    Scans all worker-specific in-progress sets and sums their counts.
    """
    try:
        total = 0
        # Find all worker in-progress sets
        keys = redis_manager.keys(IN_PROGRESS_PATTERN)
        for key in keys:
            count = redis_manager.scard(key)
            total += count
        return total
    except Exception as e:
        logger.warning(f"[SIMULATION_QUEUE] Failed to count in-progress jobs: {e}")
        # Return just this worker's count as fallback
        return redis_manager.scard(IN_PROGRESS_SET)


def get_worker_in_progress_count() -> int:
    """Get the number of jobs currently in progress for THIS worker only."""
    return redis_manager.scard(IN_PROGRESS_SET)
```

#### 2c. Add helper to get all in-progress info (optional, for debugging)

Add this new function after `get_in_progress_count`:
```python
def get_all_workers_in_progress() -> dict:
    """
    Get in-progress counts per worker (for debugging/monitoring).
    
    Returns:
        Dict mapping worker_id to count, e.g., {"worker-abc123": 3, "worker-def456": 2}
    """
    try:
        result = {}
        keys = redis_manager.keys(IN_PROGRESS_PATTERN)
        for key in keys:
            # Extract worker ID from key (simulation:in_progress:{worker_id})
            worker_id = key.split(":")[-1] if isinstance(key, str) else key.decode().split(":")[-1]
            count = redis_manager.scard(key)
            result[worker_id] = count
        return result
    except Exception as e:
        logger.warning(f"[SIMULATION_QUEUE] Failed to get worker in-progress info: {e}")
        return {WORKER_ID: redis_manager.scard(IN_PROGRESS_SET)}
```

---

### Step 3: Update tasks.py Startup Cleanup

**File:** `backend/modules/simulation/tasks.py`

Replace lines 202-221:
```python
# OLD:
    # CRITICAL: Clean up stale in-progress set on worker startup
    # This handles the case where workers crashed/restarted with jobs still marked as "in progress"
    # which causes should_use_queue() to always return True (blocking direct processing)
    try:
        from common.services.simulation_queue_service import IN_PROGRESS_SET
        from common.services.cache_service import redis_manager
        
        stale_count = redis_manager.scard(IN_PROGRESS_SET)
        if stale_count > 0:
            logger.warning(
                f"[SIMULATION_WORKER] Cleaning up {stale_count} stale in-progress job(s) "
                f"from previous worker instance"
            )
            redis_manager.delete(IN_PROGRESS_SET)
            logger.info("[SIMULATION_WORKER] ✓ Stale in-progress set cleared")
        else:
            logger.info("[SIMULATION_WORKER] No stale in-progress jobs to clean up")
    except Exception as e:
        logger.error(f"[SIMULATION_WORKER] Failed to clean up stale in-progress set: {e}")
```

With:
```python
# NEW:
    # CRITICAL: Clean up only THIS worker's stale in-progress set on startup
    # Each worker has its own set (keyed by WORKER_ID), so we only clean our own
    # This is safe in multi-replica deployments - other workers' jobs are untouched
    try:
        from common.services.simulation_queue_service import IN_PROGRESS_SET, WORKER_ID
        from common.services.cache_service import redis_manager
        
        stale_count = redis_manager.scard(IN_PROGRESS_SET)
        if stale_count > 0:
            # Get the stale job IDs for logging before deletion
            stale_jobs = redis_manager.smembers(IN_PROGRESS_SET)
            stale_job_ids = [j.decode() if isinstance(j, bytes) else j for j in stale_jobs]
            
            logger.warning(
                f"[SIMULATION_WORKER] Worker {WORKER_ID}: Cleaning up {stale_count} stale "
                f"in-progress job(s) from previous instance: {stale_job_ids[:5]}..."  # Log first 5
            )
            redis_manager.delete(IN_PROGRESS_SET)
            logger.info(f"[SIMULATION_WORKER] ✓ Worker {WORKER_ID}: Stale in-progress set cleared")
        else:
            logger.info(f"[SIMULATION_WORKER] Worker {WORKER_ID}: No stale in-progress jobs to clean up")
    except Exception as e:
        logger.error(f"[SIMULATION_WORKER] Failed to clean up stale in-progress set: {e}")
```

---

### Step 4: Update Logging in tasks.py

**File:** `backend/modules/simulation/tasks.py`

Update line 199-200 to include worker ID:
```python
# OLD:
    logger.info("[SIMULATION_WORKER] Starting simulation queue worker")
    logger.info(f"[SIMULATION_WORKER] Worker configuration: MAX_CONCURRENT_JOBS={MAX_CONCURRENT_JOBS}, POLL_INTERVAL={POLL_INTERVAL}")
```

With:
```python
# NEW:
    from common.services.simulation_queue_service import WORKER_ID
    logger.info(f"[SIMULATION_WORKER] Starting simulation queue worker (WORKER_ID={WORKER_ID})")
    logger.info(f"[SIMULATION_WORKER] Worker configuration: MAX_CONCURRENT_JOBS={MAX_CONCURRENT_JOBS}, POLL_INTERVAL={POLL_INTERVAL}")
```

---

### Step 5: Railway Configuration (No Action Needed!)

Railway automatically provides `RAILWAY_REPLICA_ID` for each replica. **No manual configuration required.**

Each replica will automatically get:
- Replica 0 → `RAILWAY_REPLICA_ID=0` → Redis key: `simulation:in_progress:0`
- Replica 1 → `RAILWAY_REPLICA_ID=1` → Redis key: `simulation:in_progress:1`
- Replica 2 → `RAILWAY_REPLICA_ID=2` → Redis key: `simulation:in_progress:2`
- ...and so on

---

## Files Changed Summary

| File | Changes |
|------|---------|
| `backend/common/config.py` | Add `worker_id` property to Settings |
| `backend/common/services/simulation_queue_service.py` | Make `IN_PROGRESS_SET` worker-specific, update `get_in_progress_count()` |
| `backend/modules/simulation/tasks.py` | Update cleanup to only delete this worker's set |

---

## Testing Checklist

- [ ] Single worker: Jobs are tracked in `simulation:in_progress:{worker_id}`
- [ ] Single worker: `get_in_progress_count()` returns correct count
- [ ] Single worker: Worker restart cleans up only its own stale jobs
- [ ] Multi-replica: Each worker has separate in-progress set
- [ ] Multi-replica: `get_in_progress_count()` aggregates across all workers
- [ ] Multi-replica: Worker restart doesn't affect other workers' in-progress jobs
- [ ] `should_use_queue()` still makes correct routing decisions

---

## Redis Key Structure (After Implementation)

```
simulation:in_progress:0               # Replica 0's in-progress jobs (SET)
simulation:in_progress:1               # Replica 1's in-progress jobs (SET)
simulation:in_progress:2               # Replica 2's in-progress jobs (SET)
simulation:in_progress:local-abc123    # Local dev worker (SET) - fallback ID
simulation_queue                       # Shared job queue (LIST)
simulation:job:{job_id}                # Job data (STRING)
simulation:status:{job_id}             # Job status (STRING)
simulation:result:{job_id}             # Job result (STRING)
```

---

## Capacity Planning for 100+ Concurrent Users

### Recommended Replica Configuration

| Replicas | Use Case | Monthly Cost (approx) |
|----------|----------|----------------------|
| 2 | Good starting point with redundancy | ~$10-20 |
| 3 | Better burst handling, recommended for 100 users | ~$15-30 |
| 4 | High availability, 150+ users | ~$20-40 |
| 8 | Overkill for 100 users, consider reducing | ~$40-80 |

### Configuration in `backend_railway.toml`

```toml
[deploy]
numReplicas = 3   # Start with 3 for 100 concurrent users
```

### Key Bottlenecks to Monitor

1. **AI API rate limits** — Usually the real bottleneck, not replicas
2. **Database connections** — Ensure connection pooling is configured
3. **Redis connections** — Monitor connection count
4. **Memory per replica** — Watch for OOM errors in logs

---

## Rollback Plan

If issues arise, revert by:
1. Change `IN_PROGRESS_SET` back to `"simulation:in_progress"` (remove worker ID suffix)
2. Remove `WORKER_ID` constant
3. Revert `get_in_progress_count()` to simple `scard()` call
4. Clean up any worker-specific keys: `redis-cli KEYS "simulation:in_progress:*" | xargs redis-cli DEL`

---

## Related Links

- [Railway Horizontal Scaling Docs](https://docs.railway.com/guides/optimize-performance#configure-horizontal-scaling)
- [RAILWAY_REPLICA_ID Environment Variable](https://docs.railway.com/guides/optimize-performance#replica-id-environment-variable)
- CodeRabbit Issue: PR review comment on `tasks.py:202-221`
