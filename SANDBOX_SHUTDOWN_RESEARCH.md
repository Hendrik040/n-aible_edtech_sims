# Sandbox Shutdown Research — Gaps & Implementation Plan

## Executive Summary

The current Daytona sandbox implementation has **5 identified exit paths where sandboxes are NOT cleaned up**, leading to unnecessary compute costs. The Daytona SDK charges for:
- **Running sandboxes** (full compute cost)
- **Stopped sandboxes** (disk-only cost)
- **Archived sandboxes** (object storage cost, cheapest)

Only **deleted** sandboxes incur zero cost. Our current safety nets (auto-stop at 60min, auto-delete at 24h) are too generous and leave sandboxes running/existing far longer than needed.

---

## Current State: Where Sandboxes ARE Cleaned Up

| Exit Path | Cleanup? | Location |
|-----------|----------|----------|
| Simulation completes normally (submit for grading on final scene) | Yes | `service.py:134-143` |
| Simulation completes via timeout (max turns reached during chat) | Yes | `chat_handler.py:741-751` |
| Daytona auto-stop after 60 min idle | Partial (stops, doesn't delete) | Daytona-managed |
| Daytona auto-archive after 120 min stopped | Partial (archives, doesn't delete) | Daytona-managed |
| Daytona auto-delete after 24h | Yes (but very late) | Daytona-managed |

## Current State: Where Sandboxes are NOT Cleaned Up

### Gap 1: Student Resets Simulation
**File:** `backend/modules/student/routers/student_instances.py:913-1032`

When a student resets a completed simulation, the code:
1. Calls `repository.delete_all_user_progress_for_simulation()` — which **deletes the UserProgress row** containing `sandbox_id`
2. Starts a fresh simulation (which may create a NEW sandbox)

**The old sandbox is never deleted.** The `sandbox_id` is lost when the UserProgress row is deleted. The sandbox will sit running/stopped until Daytona auto-deletes it after 24 hours.

**Impact:** Each reset creates an orphaned sandbox burning compute for up to 24h.

### Gap 2: Professor Re-publishes / Cohort Reassignment
**File:** `backend/modules/cohorts/service.py:620-659`

When a professor reassigns a simulation to a cohort, the code:
1. Calls `repo.delete_user_progress_and_related(existing_instance.user_progress_id)` — which deletes UserProgress
2. Resets instance fields

**Same problem:** The `sandbox_id` on UserProgress is never read before deletion, so the Daytona sandbox is orphaned.

### Gap 3: Browser Tab Close / Session Abandonment
**No handler exists.** If a student simply closes their browser mid-simulation, the sandbox keeps running at full compute cost until the 60-minute auto-stop kicks in (then sits stopped for another 23 hours until auto-delete).

There is no:
- WebSocket disconnect handler that cleans up sandboxes
- Periodic background task that checks for stale sandboxes
- Heartbeat mechanism to detect abandoned sessions

### Gap 4: Server Restart / Deployment
**File:** `backend/app/lifespan.py`

On application startup, there is **no orphan sandbox cleanup**. The lifespan handler starts background workers for image uploads, simulation queues, Redis pub/sub, and session cleanup — but never queries for stale `sandbox_id` values in the database.

If the server crashes or restarts, any sandbox that was active remains running on Daytona's side with no way to clean it up until auto-delete (24h later).

### Gap 5: `delete_user_progress_and_related()` Doesn't Clean Up Sandbox
**File:** `backend/modules/simulation/repository.py:108-147`

This is the root cause behind Gaps 1 and 2. The method deletes UserProgress rows via raw SQL, never checking for or cleaning up associated Daytona sandboxes. Since it's a synchronous method operating inside a DB transaction, it can't easily call the async `sandbox_service.delete_sandbox()`.

---

## Daytona SDK Capabilities (Research Findings)

### Sandbox Lifecycle States
```
Created → Started → Stopped → Archived → Deleted
                  ↘ Deleted   ↗ Started
                  Stopped → Started (resume)
                  Archived → Started (cold start, slower)
```

### Cost Model
| State | Cost |
|-------|------|
| Started (running) | Full compute |
| Stopped | Disk-only |
| Archived | Object storage (cheapest non-zero) |
| Deleted | Zero |

### Key SDK Methods Available
```python
# Already used
await daytona.create(params)        # Create sandbox
await daytona.get(sandbox_id)       # Get sandbox by ID
await daytona.delete(sandbox)       # Delete sandbox
sandbox.code_interpreter.run_code() # Execute code

# NOT yet used — available for cleanup
await daytona.list(labels={...})    # List sandboxes by labels
await daytona.find_one(labels={..}) # Find one sandbox by labels
await sandbox.stop(timeout=60)     # Stop sandbox (keep disk)
await sandbox.start(timeout=60)    # Restart stopped sandbox
sandbox.set_autostop_interval(min) # Change auto-stop dynamically
```

### Labels System
Sandboxes can be created with key-value **labels** for organization and filtering:
```python
params = CreateSandboxFromImageParams(
    image=...,
    labels={"app": "naible", "user_id": "123", "simulation_id": "456"}
)
```
This enables querying all sandboxes belonging to our application for bulk cleanup.

---

## Recommended Implementation Plan

### Priority 1: Immediate Wins (Low effort, high impact)

#### 1A. Reduce Auto-Stop from 60 → 15 minutes
Simulations are interactive. If a student hasn't executed code in 15 minutes, the sandbox should stop. A stopped sandbox can be restarted transparently on the next code execution.

```python
# sandbox_service.py - change auto_stop_interval
params = CreateSandboxFromImageParams(
    image=self._get_sandbox_image(),
    language="python",
    auto_stop_interval=15,       # Was 60
    auto_archive_interval=60,    # Was 120
    auto_delete_interval=360,    # Was 1440 (24h) → 6h
)
```

**Savings:** Reduces worst-case idle compute from 60 min to 15 min per session.

#### 1B. Reduce Auto-Delete from 24h → 6h
No simulation should ever need a sandbox for 24 hours. 6 hours is generous.

#### 1C. Add Labels to Sandbox Creation
Tag sandboxes with app identity and user context so we can find/list them:
```python
params = CreateSandboxFromImageParams(
    image=self._get_sandbox_image(),
    language="python",
    labels={
        "app": "naible-edtech",
        "user_id": str(user_id),       # Need to pass this in
        "simulation_id": str(sim_id),  # Need to pass this in
    },
    auto_stop_interval=15,
    auto_archive_interval=60,
    auto_delete_interval=360,
)
```

### Priority 2: Fix Orphan-Creating Paths (Medium effort, high impact)

#### 2A. Clean Up Sandbox Before Deleting UserProgress
Before `delete_user_progress_and_related()` or `delete_all_user_progress_for_simulation()` is called, read the `sandbox_id` and schedule deletion:

**In `student_instances.py` (reset simulation):**
```python
# BEFORE deleting progress, clean up sandbox
if instance.user_progress_id:
    user_progress = db.query(UserProgress).get(instance.user_progress_id)
    if user_progress and user_progress.sandbox_id:
        from common.services.sandbox_service import sandbox_service
        await sandbox_service.delete_sandbox(user_progress.sandbox_id)
```

**In `cohorts/service.py` (reassignment):**
Same pattern — read sandbox_id before deleting progress, schedule deletion.

#### 2B. Add `stop_sandbox()` Method to SandboxService
For cases where we want to stop billing immediately but might resume later:
```python
async def stop_sandbox(self, sandbox_id: str) -> bool:
    """Stop a sandbox. Clears memory but keeps disk. Can be restarted."""
    if not self.enabled:
        return False
    try:
        sandbox = await self.daytona.get(sandbox_id)
        await sandbox.stop(timeout=60)
        logger.info(f"[DAYTONA] Stopped sandbox {sandbox_id}")
        return True
    except Exception as e:
        logger.error(f"[DAYTONA] Failed to stop sandbox {sandbox_id}: {e}")
        return False
```

#### 2C. Add `start_sandbox()` for Resuming Stopped Sandboxes
When a student returns to a stopped sandbox, transparently restart it:
```python
async def start_sandbox(self, sandbox_id: str) -> bool:
    """Start a previously stopped sandbox."""
    if not self.enabled:
        return False
    try:
        sandbox = await self.daytona.get(sandbox_id)
        await sandbox.start(timeout=120)
        logger.info(f"[DAYTONA] Restarted sandbox {sandbox_id}")
        return True
    except Exception as e:
        logger.error(f"[DAYTONA] Failed to start sandbox {sandbox_id}: {e}")
        return False
```

Then in the execute-code endpoint, if execution fails with a "sandbox stopped" error, try restarting.

### Priority 3: Startup Orphan Cleanup (Medium effort, prevents accumulation)

#### 3A. Add Orphan Cleanup to App Startup
In `lifespan.py`, add a startup task that finds and deletes orphaned sandboxes:

```python
async def _cleanup_orphaned_sandboxes():
    """On startup, delete sandboxes for completed/stale simulations."""
    from common.services.sandbox_service import sandbox_service
    if not sandbox_service.enabled:
        return

    from common.db.core import SessionLocal
    from common.db.models.simulation.user_progress import UserProgress

    db = SessionLocal()
    try:
        # Find all UserProgress rows with sandbox_id that are completed or stale
        from datetime import datetime, timedelta, timezone
        stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)

        orphans = db.query(UserProgress).filter(
            UserProgress.sandbox_id.isnot(None),
            # Either completed or no recent activity
            (UserProgress.simulation_status == "completed") |
            (UserProgress.updated_at < stale_cutoff)
        ).all()

        for progress in orphans:
            try:
                await sandbox_service.delete_sandbox(progress.sandbox_id)
                progress.sandbox_id = None
                logger.info(f"[STARTUP] Cleaned orphaned sandbox for progress {progress.id}")
            except Exception as e:
                logger.warning(f"[STARTUP] Failed to clean sandbox {progress.sandbox_id}: {e}")

        db.commit()
        logger.info(f"[STARTUP] Orphan sandbox cleanup complete: {len(orphans)} found")
    finally:
        db.close()
```

#### 3B. Periodic Sandbox Audit (Background Task)
Add a background task (like the existing session cleanup) that runs every 30 minutes:

```python
async def _sandbox_cleanup_task():
    """Periodically find and clean up stale sandboxes."""
    while True:
        try:
            await _cleanup_orphaned_sandboxes()
        except Exception as e:
            logger.error(f"Error in sandbox cleanup task: {e}")
        await asyncio.sleep(1800)  # Every 30 minutes
```

#### 3C. Use Daytona `list()` for Comprehensive Cleanup
With labels (Priority 1C), we can also query Daytona directly for all our sandboxes and cross-reference with the database to find any that shouldn't exist:

```python
async def cleanup_all_orphaned_sandboxes(self) -> int:
    """List all our sandboxes on Daytona and delete any that are orphaned."""
    if not self.enabled:
        return 0

    all_sandboxes = await self.daytona.list(labels={"app": "naible-edtech"})
    # Cross-reference with DB to find orphans
    # Delete any that don't have an active UserProgress row
```

### Priority 4: Session Abandonment Detection (Higher effort, nice-to-have)

#### 4A. Frontend Heartbeat
Add a periodic heartbeat from the frontend (e.g., every 5 minutes) that pings the backend. If no heartbeat is received for 15+ minutes, proactively stop the sandbox.

#### 4B. `beforeunload` / `visibilitychange` Handler
Send a "session ending" signal when the browser tab is closed:
```typescript
// In simulation page
useEffect(() => {
    const handleUnload = () => {
        navigator.sendBeacon('/api/proxy/simulation/end-session',
            JSON.stringify({ user_progress_id }));
    };
    window.addEventListener('beforeunload', handleUnload);
    return () => window.removeEventListener('beforeunload', handleUnload);
}, []);
```

This is best-effort (not guaranteed to fire) but catches the common case.

---

## Cost Impact Estimate

| Scenario | Current Waste | After Fixes |
|----------|--------------|-------------|
| Normal completion | 0 min | 0 min |
| Timeout completion | 0 min | 0 min |
| Student closes tab | Up to 60 min running + 23h stopped | 15 min running + 5h45m stopped |
| Student resets sim | Up to 24h (orphaned) | 0 min (deleted before reset) |
| Professor reassign | Up to 24h (orphaned) | 0 min (deleted before reassign) |
| Server restart | Up to 24h per sandbox | 0 min (cleaned on startup) |
| Repeated testing (dev) | Hits 30GB disk limit | Aggressive cleanup prevents limit |

**With all Priority 1-3 fixes:** Reduces worst-case sandbox waste from **24 hours to ~15 minutes** per session, and eliminates all orphaned sandbox scenarios.

---

## Files That Need Changes

| File | Change | Priority |
|------|--------|----------|
| `backend/common/services/sandbox_service.py` | Reduce intervals, add labels, add `stop_sandbox()`/`start_sandbox()`/`cleanup_all_orphaned_sandboxes()` | P1, P2 |
| `backend/modules/student/routers/student_instances.py` | Clean up sandbox before reset | P2 |
| `backend/modules/cohorts/service.py` | Clean up sandbox before reassignment | P2 |
| `backend/app/lifespan.py` | Add orphan cleanup on startup + periodic task | P3 |
| `backend/modules/simulation/router.py` | Handle stopped-sandbox restart on execute | P2 |
| `frontend/app/student/run-simulation/[instanceId]/page.tsx` | Add `beforeunload` handler | P4 |

---

## References
- [Daytona Sandbox Management](https://www.daytona.io/docs/en/sandbox-management/)
- [Daytona Python SDK - Daytona Class](https://www.daytona.io/docs/en/python-sdk/sync/daytona/)
- [Daytona Python SDK - AsyncSandbox](https://www.daytona.io/docs/en/python-sdk/async/async-sandbox/)
- [Daytona Sandboxes Overview](https://www.daytona.io/docs/en/sandboxes/)
- [Daytona Python SDK Reference](https://www.daytona.io/docs/en/python-sdk/)
