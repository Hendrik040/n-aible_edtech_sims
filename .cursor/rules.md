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

## Next Actions (Auth Phase)
1. Implement JWT/password utilities (likely `modules/auth/utils.py`).
2. Build `service.py` around DB interactions + cookie responses.
3. Port existing `/users/register` and `/users/login` logic into `router.py` using new service.
4. Wire router into `app/main.py` (or `app/routers/auth.py` once created).
5. After auth works, document dependency usage in `app/dependencies.py`.
