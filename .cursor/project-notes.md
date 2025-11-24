# Project Notes

## Backend Architecture Snapshot
- FastAPI entrypoint: `backend/app/main.py`; routers mounted via `app/api/__init__.py` which wires auth, simulation, pdf processing, professor, student, publishing, and notifications domains.
- Shared infrastructure:
  - `backend/common/config.py`: Pydantic settings + environment validation.
  - `backend/common/db/`: `base.py`, `core.py`, and mixins for SQLAlchemy setup.
  - `backend/common/utils/`: auth, security, redis, rate limiter, etc.
- Feature modules live under `backend/modules/<domain>/` and each owns `router.py`, `service.py`, `repository.py`, and `schemas/` (DTO + ORM). Simulation also hosts `agents/` and background chat orchestrator.
- Tests mirror modules via `backend/tests/modules/...` (expansion planned as refactor progresses).

## Key Services
- Email + notification helpers remain under `backend/services/` (e.g., `email_service.py`, `notification_service.py`, `session_manager.py`). Simulation-specific business logic now resides inside `modules/simulation/` instead of the deleted `services/simulation_engine.py`.

## Commands & Environment
- Backend expects Python 3.11+ with FastAPI/Uvicorn; run via `uvicorn backend.app.main:app --reload` after activating the repo's virtualenv.
- Load `.env` in repo root (used by `common/config.py`). Production validation enforces Google OAuth + S3/Wasabi credentials.

## Cleanup Notes
- Legacy directories `backend/api/`, `backend/agents/`, `backend/app/router/`, and `backend/common/utilities/` were removed; imports should only reference `modules.*` or `common.*` now.
- AST scan script (see repo root command history) ensures no `api.*` / `agents.*` imports linger.
