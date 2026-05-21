# Cursor Rules & Context

## Architecture Snapshot
- Target structure: `app/` (wiring), `common/` (shared infra), `modules/` (feature slices), `tests/`.
- Dependency flow: `app → modules → common`; modules never import each other.
- Shared infra implemented: config, logging, DB connection, utils (`id_generator`).
- Models & schemas centralized under `common/db/` but split into per-domain files.

## Current Progress
- `common/config.py`, `common/logging.py`, `common/db/connection.py` live and wired.
- Model package scaffolded with `user.py` implemented; other domain files are placeholders.
- Schema package mirrors this; `user` and `auth` schemas ready.
- `app/main.py` exists with health + root endpoints and logging setup.

## Migration Strategy
1. **Skeleton first**: keep infra minimal and bootable before moving features.
2. **Vertical slices**: migrate Auth end-to-end (models/schemas already ready) before touching Simulation, etc.
3. **Repositories later**: keep DB access inside services until each module stabilizes, then extract repositories.
4. **Shared utilities**: only move helpers into `common/utils/` when they’re clearly cross-module (e.g., JWT/password hashing).
5. **Testing**: mirror production structure (`tests/modules/auth/...`) once each slice has baseline functionality.

## Auth Module Game Plan
- `modules/auth/router.py`: login, register, OAuth endpoints (thin layer).
- `modules/auth/service.py`: password flow, JWT creation/verification, cookie handling.
- `modules/auth/provider.py`: Google OAuth helpers (state store, token exchange).
- Decide soon: keep `get_current_user` in `modules/auth` vs. move to `app/dependencies.py`.

## Guardrails
- Keep files <300 lines; split routers/services if they grow.
- Use string-based SQLAlchemy relationships to avoid circular imports.
- Ensure every model imports `Base` from `common/db/connection.py`.
- Run tests and lint on each slice before moving on.

## Performance Guidelines (CRITICAL)

This codebase uses NullPool for PgBouncer compatibility, meaning **each query creates a new connection (~50-100ms overhead)**. Reducing query count is the most effective optimization.

### Database Queries - Avoid N+1!
```python
# ❌ BAD: N+1 queries (loops create separate queries)
for item in items:
    related = db.query(Related).filter(item_id == item.id).all()

# ✅ GOOD: Single batched query with IN clause
all_related = db.query(Related).filter(Related.item_id.in_([i.id for i in items])).all()
related_by_item_id = {}
for r in all_related:
    related_by_item_id.setdefault(r.item_id, []).append(r)
```

### SQLAlchemy Eager Loading
```python
# ✅ Use selectinload for relationships
from sqlalchemy.orm import selectinload
query = db.query(Simulation).options(
    selectinload(Simulation.personas),
    selectinload(Simulation.scenes)
)
```

### Redis Caching
- Cache frequently accessed data (TTL: 60-300s depending on freshness needs)
- **Always invalidate cache on mutations** (create, update, delete)
- Use user-specific cache keys: `user:{id}:resource:params`
```python
cache_key = f"user:{user_id}:simulations:drafts={include_drafts}"
cached = cache_service.get(cache_key)
if cached:
    return cached
# ... fetch from DB ...
cache_service.set(cache_key, result, ttl=300)
```

### Frontend API Calls
- **Consolidate** multiple similar API calls into single requests with query params
- Use `useRef` to prevent duplicate fetches in React StrictMode:
```typescript
const fetchInitiatedRef = useRef(false)
useEffect(() => {
  if (fetchInitiatedRef.current) return
  fetchInitiatedRef.current = true
  fetchData()
}, [user?.id])  // Use stable primitives, not objects
```
- Prefer using data already in responses vs. making additional API calls

### Async Operations
- Use `asyncio.gather()` for parallel I/O-bound operations (e.g., S3 checks)
- Single DB commit after batch operations, not per-item

## Next Actions (Auth Phase)
1. Implement JWT/password utilities (likely `modules/auth/utils.py`).
2. Build `service.py` around DB interactions + cookie responses.
3. Port existing `/users/register` and `/users/login` logic into `router.py` using new service.
4. Wire router into `app/main.py` (or `app/routers/auth.py` once created).
5. After auth works, document dependency usage in `app/dependencies.py`.
