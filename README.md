# develop-v2 Backend Skeleton

This directory hosts an isolated refactor spike of the backend architecture described in `n-aible_edtech_sims/architecture.md`. The goal is to provide a clean, modular baseline that other contributors can implement domain-by-domain without dragging along legacy code.

## Current Scope
- Auth vertical has working scaffolding (`modules/auth`) with minimal service logic and FastAPI wiring.
- All other domains (simulation, PDF processing, professor, student, notifications, publishing) exist as placeholder packages (`router.py`, `service.py`, `repository.py`, `schemas/dto.py`, `schemas/models.py`, `tasks.py`) containing comments about their intended responsibilities.
- Shared infrastructure under `backend/common/` (config, db core, utilities, services) mirrors the target structure but only contains lightweight stubs where implementation is still pending.

## Getting Started
1. **Install dependencies**
   ```bash
   cd develop-v2/backend
   uv sync  # or pip install -r requirements.txt once defined
   ```
   The current linter warnings stem from missing packages such as `fastapi`, `sqlalchemy`, `passlib`, and `python-jose`.

2. **Run the app**
   ```bash
   uvicorn backend.app.main:app --reload
   ```
   This spins up the skeleton API (currently only `/api/auth/*` and `/health`).

3. **Database**
   - Defaults to SQLite via `common/config.py` (see `database_url`).
   - `app/main.py` calls `Base.metadata.create_all()` at startup to bootstrap tables.

## Where to Continue
- **Fill in domain modules**: For each feature (simulation, pdf_processing, etc.), implement the router/service/repository layers following the architecture doc. Module directories already exist with placeholder comments.
- **Shared services**: Implement real logic inside `common/services/*` (email, cache, AI gateway) and `common/utils/*` as you pick up features that rely on them.
- **Middleware & Lifespan**: `app/middleware.py` and `app/lifespan.py` are ready for CORS, logging, dependency wiring, etc., once the broader functionality requires them.
- **Tests**: `tests/modules/<domain>/test_router.py` files mirror production structure and are currently empty placeholders—fill these as you add functionality.

## Conventions to Follow
- Keep routers thin; push business logic into `service.py`, data access into `repository.py`, and schema definitions into `schemas/`.
- Import shared resources via `backend.common.*` (no direct cross-module imports).
- Use the placeholder comments as TODO markers—replace them with actual code as you implement each slice.

This README should give the next contributor enough context to continue implementing modules without digging through the legacy repo. EOF