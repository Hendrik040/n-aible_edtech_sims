# PR #209 - Notification Modules: Issues to Address

> Summary of issues identified by CodeRabbit and Cursor Bugbot that need to be resolved before merging.

---

## 🔴 Critical Issues

### 1. Bytes vs String Handling for Redis Job Status/ID
**Location:** `backend/common/services/simulation_queue_service.py` (lines 179-203)

**Problem:** Type mismatch between how values are stored and read from Redis:
- `status` is stored as plain string but `redis_manager.get` returns bytes (e.g., `b"pending"`)
- Comparisons like `status == STATUS_PENDING` never succeed
- `job_id` from `rpop` is bytes, causing key mismatches like `"simulation:job:b'...'"` 

**Impact:**
- Queue position logic for pending jobs won't run
- `get_job_result` always short-circuits, results never returned
- Valid jobs get marked as failed due to missing job data

**Fix:** Normalize Redis reads to strings immediately after retrieval.

---

### 2. Non-Atomic Transaction for Invitation Acceptance
**Location:** `backend/modules/notifications/service.py`

**Problem:** Two separate commits:
1. `update_invitation_status` commits invitation status change
2. Service separately commits `CohortStudent` enrollment creation

**Impact:** If enrollment commit fails, invitation remains "accepted" but student isn't enrolled in cohort - inconsistent state.

**Fix:** Wrap both operations in a single transaction.

---

### 3. Timeout Check Skipped for @mention and @ALL Messages
**Location:** `backend/modules/simulation/handlers/chat_handler.py`

**Problem:** `handle_timeout` function is never called for:
- Single `@mention` messages (early return at line 484)
- `@all` messages (early return at lines 611-617)

Both paths hardcode `scene_completed: False` and `next_scene_id: None`.

**Impact:** Scene transitions based on `timeout_turns` will never trigger for the majority of chat interactions, breaking timeout-based scene progression.

---

## 🟠 Major Issues

### 4. String Formatting Produces "declineed" 
**Location:** `backend/modules/notifications/service.py`

**Problem:** Using `f"{action}ed"` produces incorrect text when `action` is "decline":
- Notification titles: "Invitation declineed"
- Notification types: "invitation_declineed"
- Response messages: "Invitation declineed successfully"

**Fix:** Handle the "decline" → "declined" case explicitly.

---

### 5. Email Masking Crashes on Empty Local Part
**Location:** `backend/modules/notifications/service.py`

**Problem:** `_mask_email` function crashes with `IndexError` when email has empty local part (e.g., `@domain.com`):
- Check `'@' not in email` passes
- `local` becomes empty string
- Accessing `local[0]` raises exception

**Impact:** Returns 500 error even though invitation status was already updated (post-commit).

---

### 6. Case-Sensitive Email Comparison
**Location:** `backend/modules/notifications/service.py`

**Problem:** Invitation verification uses case-sensitive comparison:
```python
email_match = invitation.student_email == user.email
```

But auth module uses case-insensitive comparison (`func.lower(User.email)`).

**Impact:** Invitation with "John@University.edu" won't match student registered as "john@university.edu".

**Additional Location:** `get_pending_invitations_by_email` repository query.

---

### 7. Missing Defensive Rollback in Exception Handler
**Location:** `backend/modules/simulation/tasks.py` (lines 182-189)

**Problem:** Outer `except Exception as e:` logs and re-raises but doesn't call `db.rollback()`.

**Impact:** If exception occurs outside inner commit block, session could have pending changes when `process_with_semaphore` closes it.

**Fix:** Add `db.rollback()` in exception handler.

---

### 8. Logging Imports Inside Methods
**Location:** `backend/modules/simulation/services/lifecycle_service.py` (lines 590-603)

**Problem:** `logging` module imported twice inside method, logger initialized twice.

**Fix:** Move imports to module level and initialize logger once.

---

## 🟡 Minor Issues

### 9. Empty Set Condition Causes Query Issues
**Location:** `backend/modules/cohorts/repository.py` (lines 620-625)

**Problem:** When `approved_ids_set` is empty, line 624 evaluates to Python `False` literal:
```python
StudentSimulationInstance.student_id.in_(approved_ids_set) if approved_ids_set else False
```

SQLAlchemy's `and_()` expects column expressions, not Python booleans.

**Impact:** Can cause SQL syntax errors or incorrect queries when cohort has no approved students.

**Fix:** Use `sa.false()` or `sa.literal(False)` instead, or restructure query.

---

### 10. Cache Invalidation Missing Archived Status
**Location:** `backend/modules/publishing/router.py`

**Problem:** `invalidate_user_simulations_cache` is missing patterns for `status=archived`:
- Endpoint supports filtering by `status=archived`
- Cache keys like `user:{id}:simulations:drafts=False:status=archived` exist
- But these patterns are not in invalidation list

**Impact:** When simulation is archived, stale cached list persists until 5-minute TTL expires.

---

### 11. StrictMode Protection Ref Never Reset
**Location:** `frontend/app/professor/dashboard/page.tsx` (lines 66-68)

**Problem:** `fetchInitiatedRef` prevents duplicate fetches in StrictMode but is never reset.

**Impact:** If user logs out and back in, data won't be refetched because ref remains `true`.

**Fix:** Reset ref when user changes.

---

## ✅ Checklist

- [ ] Fix Redis bytes/string handling in simulation queue service
- [ ] Make invitation acceptance atomic (single transaction)
- [ ] Add timeout check for @mention and @ALL messages
- [ ] Fix "declineed" string formatting
- [ ] Add guard for empty email local part in `_mask_email`
- [ ] Make email comparisons case-insensitive
- [ ] Add `db.rollback()` in simulation task exception handler
- [ ] Move logging imports to module level
- [ ] Fix SQLAlchemy `False` literal in `and_()` expression
- [ ] Add archived status to cache invalidation patterns
- [ ] Reset fetch ref on user logout/login

---

*Generated from PR #209 review comments - December 24, 2025*

