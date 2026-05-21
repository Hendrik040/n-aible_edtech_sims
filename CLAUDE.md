# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI Agent Education Platform - An innovative educational platform that transforms business case studies into immersive AI-powered simulations. The platform uses LangChain-based AI agents (personas) to create interactive learning experiences where students engage with AI characters through a linear simulation system orchestrated by the ChatOrchestrator.

**Tech Stack:**
- Backend: FastAPI (Python 3.11+) with SQLAlchemy, Alembic migrations
- Frontend: Next.js 15 (TypeScript) with shadcn/ui components
- Database: PostgreSQL 14+ with pgvector extension
- AI: OpenAI GPT-4 via LangChain
- Caching: Redis for session and AI response caching
- Infrastructure: Docker Compose for local development

## Development Commands

### Backend (from `/backend` directory)

**Start development server:**
```bash
# Activate virtual environment first
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Start server with hot reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Database operations:**
```bash
# Change to database directory
cd database

# Run migrations (apply all pending migrations)
alembic upgrade head

# Create new migration (after modifying models.py)
alembic revision --autogenerate -m "description of changes"

# Rollback last migration
alembic downgrade -1

# View migration history
alembic history
```

**Testing:**
```bash
# Run tests (when implemented)
pytest

# Clear database (development only - be careful!)
python clear_database.py
```

### Frontend (from `/frontend` directory)

**Development:**
```bash
# Install dependencies
pnpm install

# Start development server
pnpm dev

# Build for production
pnpm build

# Start production server
pnpm start

# Run linting
pnpm lint
```

### Docker Services

**Start/stop infrastructure:**
```bash
# Start PostgreSQL + Redis
docker-compose up -d

# View logs
docker-compose logs -f postgres redis

# Stop services
docker-compose down

# Reset database (WARNING: destroys all data!)
docker-compose down -v
docker-compose up -d
```

## Architecture

### Backend Architecture

**Core Components:**

1. **ChatOrchestrator** (`backend/api/chat_orchestrator.py`)
   - Central orchestration system for linear simulations
   - Manages scene progression and turn tracking
   - Coordinates multiple AI persona agents
   - Integrates with LangChain for enhanced AI interactions
   - Maintains simulation state across scenes

2. **AI Agents** (`backend/agents/`)
   - `PersonaAgent`: LangChain-based agents representing characters in simulations
   - `GradingAgent`: Automated grading and assessment
   - `SummarizationAgent`: Scene and conversation summarization
   - Each agent has isolated memory and session management

3. **Database Models** (`backend/database/models.py`)
   - Scenario: Base simulation template with personas and scenes
   - ScenarioPersona: AI character definitions with personality traits
   - ScenarioScene: Linear simulation stages
   - UserProgress: Student progress through simulations
   - ConversationLog: Chat history and AI interactions
   - Cohort: Professor-managed student groups
   - **Soft deletion**: Uses `deleted_at` field instead of hard deletes

4. **Services** (`backend/services/`)
   - `session_manager.py`: Manages user sessions with automatic cleanup
   - `scene_memory.py`: Context-aware memory for AI agents using pgvector
   - `ai_cache_service.py`: Redis-backed caching for AI responses
   - `db_cache_service.py`: Database query result caching
   - `notification_service.py`: Email and in-app notifications
   - `wasabi_service.py`: S3-compatible object storage (optional)

5. **API Structure** (`backend/api/`)
   - `simulation.py`: Core simulation runtime endpoints (177KB - complex!)
   - `chat_orchestrator.py`: Orchestration logic
   - `parse_pdf.py`: PDF case study parsing with LlamaIndex
   - `publishing.py`: Scenario publishing workflow
   - `professor/`: Professor-specific endpoints (cohorts, grading, invitations)
   - `student/`: Student-specific endpoints (cohorts, instances, notifications)

### Frontend Architecture

**App Router Structure** (`frontend/app/`):
- `dashboard/`: Main professor dashboard for scenario management
- `professor/`: Professor views (cohorts, grading, students)
- `student/`: Student simulation interface
- `auth/`: OAuth authentication flows
- Uses Next.js 15 App Router with server/client components

**Component Organization:**
- `components/ui/`: shadcn/ui primitives (Radix UI-based)
- `components/`: Custom application components
- `hooks/`: Custom React hooks for state management
- `lib/`: Utility functions and configurations

### Database Schema Patterns

**Key Relationships:**
- Scenario → ScenarioPersona (one-to-many)
- Scenario → ScenarioScene (one-to-many, ordered by scene_order)
- ScenarioScene ← scene_personas → ScenarioPersona (many-to-many)
- User → UserProgress → ConversationLog (simulation history)
- Cohort → CohortMembership → User (professor-student relationships)

**Important Fields:**
- `deleted_at`: Soft deletion timestamp (check for NULL when querying)
- `completion_status`: Tracks scenario creation workflow progress
- `status`: "draft" vs "active" for scenarios
- `is_draft`: Boolean flag for draft scenarios
- `published_version_id`: Links draft to published version

### Authentication & Authorization

**JWT Token Flow:**
- HttpOnly cookies for token storage (secure, not accessible via JS)
- 30-minute token expiration (`ACCESS_TOKEN_EXPIRE_MINUTES`)
- Cookie settings adjust based on environment (secure=true in production)
- OAuth integration via Google (optional)

**Role-Based Access:**
- `role` field in User model: "student", "professor", "admin"
- Middleware: `middleware/role_auth.py`
- Use `get_current_user()` dependency for protected endpoints
- Use `require_admin()` for admin-only endpoints

### Memory & Context Management

**LangChain Integration:**
- Vectorstore: PostgreSQL with pgvector extension for semantic search
- Scene memory: Stores and retrieves relevant context for AI agents
- Session isolation: Each persona gets unique session ID
- Memory types: ConversationBufferWindowMemory for recent context

**Redis Caching:**
- AI responses cached to reduce API costs
- Database queries cached for performance
- Session data stored with automatic TTL
- Use `redis_manager` for all Redis operations

## Important Patterns & Conventions

### Soft Deletion
Always filter by `deleted_at.is_(None)` when querying Scenario, ScenarioPersona, or related entities:
```python
scenarios = db.query(Scenario).filter(
    Scenario.deleted_at.is_(None)
).all()
```

### Scene Order
Scenes must be ordered by `scene_order` field for linear progression:
```python
scenes = db.query(ScenarioScene).filter(
    ScenarioScene.scenario_id == scenario_id
).order_by(ScenarioScene.scene_order).all()
```

### Session Management
When creating simulations or AI interactions:
1. Generate unique session ID
2. Initialize orchestrator with session_id
3. Use session_id for all related AI agent calls
4. Cleanup happens automatically via background tasks

### Database Migrations
- Always use Alembic for schema changes
- Work from `backend/database/` directory
- Test migrations in development before production
- Use `alembic upgrade head` in production deployment

### Environment Configuration
Critical environment variables (set in `.env`):
- `DATABASE_URL`: PostgreSQL connection string
- `OPENAI_API_KEY`: Required for AI features
- `ANTHROPIC_API_KEY`: Optional secondary AI provider
- `REDIS_URL`: Redis connection (defaults to localhost:6379)
- `SECRET_KEY`: JWT signing key (must be secure in production)
- `ENVIRONMENT`: "development" or "production"
- `CORS_ORIGINS`: Comma-separated allowed origins

### Error Handling
- Use HTTPException for API errors with appropriate status codes
- Log errors via `debug_log()` utility for debugging
- Global exception handler ensures JSON responses
- Never expose internal errors to users in production

### PDF Processing
- Uses LlamaIndex for PDF parsing (`parse_pdf.py`)
- WebSocket-based progress updates (`pdf_progress.py`)
- Extracts: personas, scenes, learning objectives
- Session-based: unique session_id per upload

## Testing & Debugging

### Debug Endpoints (Development Only)
```
GET  /api/test              - Basic health check
GET  /api/test-auth         - Test authentication
GET  /api/test-db           - Test database connection
GET  /health                - Health check for monitoring
```

### Database Admin Tool
```bash
cd backend/db_admin
python simple_viewer.py  # Simple database viewer
python app.py            # Full admin interface
```

### Common Issues

**Authentication fails:**
- Check cookie settings (secure, samesite)
- Verify `SECRET_KEY` is set
- Check token expiration (30min default)

**Database connection errors:**
- Ensure PostgreSQL is running: `docker-compose ps`
- Verify `DATABASE_URL` in `.env`
- Check pgvector extension: `psql -c "CREATE EXTENSION IF NOT EXISTS vector;"`

**Redis connection failures:**
- Check Redis status: `docker-compose logs redis`
- Verify `REDIS_URL` configuration
- Redis is required for caching and sessions

**Migration conflicts:**
- Check current revision: `alembic current`
- View history: `alembic history`
- Resolve manually or rollback: `alembic downgrade -1`

## Development Workflow

### Adding a New Feature

1. **Backend:**
   - Add/modify models in `database/models.py`
   - Create migration: `cd database && alembic revision --autogenerate -m "add feature"`
   - Add schemas in `database/schemas.py`
   - Create API endpoints in appropriate `api/` subdirectory
   - Test with `/docs` (FastAPI auto-generated docs)

2. **Frontend:**
   - Add UI components in `components/`
   - Create pages in `app/` following App Router conventions
   - Use existing hooks from `hooks/` or create new ones
   - Follow shadcn/ui patterns for consistency

3. **Database:**
   - Always use Alembic migrations
   - Test migration up and down: `alembic upgrade +1` / `alembic downgrade -1`
   - Consider soft deletion for user-facing data

### Working with AI Agents

When modifying or extending AI agent behavior:
- PersonaAgent system prompts defined in `ScenarioPersona.system_prompt`
- Few-shot examples managed via `services/few_shot_examples.py`
- Memory and context retrieved via `scene_memory_manager`
- Always provide session_id for context isolation
- Test with small scenarios first to avoid high API costs

### Running in Production

The application auto-runs migrations on startup in production mode:
- Set `ENVIRONMENT=production`
- Migrations run via `alembic upgrade head` on startup
- Check logs for migration success/failure
- Fallback: manually run migrations before deployment

## File Locations Reference

**Key Files:**
- Main app: `backend/main.py` (1316 lines - entry point)
- Database models: `backend/database/models.py` (large, complex schema)
- Connection config: `backend/database/connection.py`
- Orchestrator: `backend/api/chat_orchestrator.py`
- Simulation runtime: `backend/api/simulation.py` (177KB - most complex)
- Auth utilities: `backend/utilities/auth.py`
- Frontend config: `frontend/package.json`, `frontend/next.config.js`
- Docker setup: `docker-compose.yml` (PostgreSQL + Redis)

**Environment:**
- Template: `env_template.txt`
- Actual: `.env` (not in git, create from template)