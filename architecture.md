# Backend Architecture - Simplified Modular Design

## Overview

This document proposes a new backend architecture for the n-gage platform. The approach emphasizes a simplified, feature-based structure that favors pragmatic organization over strict layering, making the system easier to develop, maintain, and evolve while upholding clear boundaries between components.

## Design Philosophy

- **Feature-based organization**: Code is grouped by business capability (simulation, PDF processing, auth) rather than technical layer
- **Minimal indirection**: Fewer layers mean faster development and easier debugging
- **Shared infrastructure**: Common concerns (DB, config, logging) live in one place
- **Incremental migration**: Structure allows gradual refactoring from current codebase

---

## Directory Structure

```
backend/
├── app/                          # FastAPI application framework
│   ├── __init__.py
│   ├── main.py                   # Application entry point (uvicorn runner)
│   ├── dependencies.py           # Dependency injection (get_db, get_current_user, etc.)
│   ├── middleware.py             # CORS, auth middleware, error handling
│   ├── routers/                  # Thin wiring layer (imports module routers)
│   │   ├── __init__.py
│   │   ├── simulation.py         # Imports from modules.simulation.router
│   │   ├── pdf_processing.py     # Imports from modules.pdf_processing.router
│   │   ├── auth.py               # Imports from modules.auth.router
│   │   ├── professor.py          # Imports from modules.professor.router
│   │   └── student.py            # Imports from modules.student.router
│   └── lifespan.py               # Startup/shutdown hooks (DB init, cleanup tasks)
│
├── common/                       # Shared infrastructure & utilities
│   ├── __init__.py
│   ├── config.py                 # Pydantic settings (env vars, app config)
│   ├── logging.py                # Structured logging setup
│   ├── exceptions.py             # Custom exception classes
│   ├── db/                       # Database layer
│   │   ├── __init__.py
│   │   ├── connection.py         # SQLAlchemy engine, session factory
│   │   ├── base.py               # SQLAlchemy declarative base
│   │   ├── models.py             # Backward compatibility (re-exports from models/)
│   │   ├── models/                # SQLAlchemy ORM models organized by module
│   │   │   ├── __init__.py       # Re-exports all models
│   │   │   ├── auth/             # Authentication models
│   │   │   │   ├── __init__.py
│   │   │   │   └── user.py      # User model
│   │   │   ├── publishing/       # Publishing models
│   │   │   │   ├── __init__.py
│   │   │   │   ├── scenario.py  # Scenario, ScenarioPersona, ScenarioScene
│   │   │   │   ├── review.py    # ScenarioReview
│   │   │   │   └── file.py      # ScenarioFile
│   │   │   ├── pdf_processing/   # PDF processing models (future)
│   │   │   ├── simulation/       # Simulation models (future)
│   │   │   ├── professor/       # Professor models (future)
│   │   │   ├── student/         # Student models (future)
│   │   │   └── notifications/   # Notification models (future)
│   │   ├── schemas.py            # Pydantic schemas (request/response models)
│   │   └── migrations/           # Alembic migrations (existing)
│   ├── services/                 # Cross-cutting services
│   │   ├── __init__.py
│   │   ├── email_service.py      # Email sending (SMTP/SendGrid)
│   │   ├── cache_service.py      # Unified caching (Redis + in-memory fallback)
│   │   └── ai_gateway.py         # Unified AI service interface (OpenAI, LangChain)
│   ├── security/                 # Security utilities
│   │   ├── __init__.py
│   │   ├── tokens.py             # JWT token generation and decoding
│   │   └── passwords.py          # Password hashing and verification
│   └── utils/                    # Helper utilities
│       ├── __init__.py
│       ├── security.py           # Security helpers (rate limiting, validation)
│       └── id_generator.py       # ID generation utilities
│
├── modules/                      # Feature modules (business logic)
│   ├── __init__.py
│   ├── simulation/               # Simulation feature
│   │   ├── __init__.py
│   │   ├── router.py             # FastAPI router (HTTP endpoints, delegates to service)
│   │   │                          # If large, split into routers/ subfolder
│   │   ├── service.py            # Business logic (orchestrates agents, validates goals)
│   │   ├── repository.py         # Data access (queries for scenarios, progress)
│   │   ├── schemas.py            # Feature-specific Pydantic models
│   │   ├── tasks.py              # Background tasks (cleanup, analytics)
│   │   └── agents/               # AI agents for simulation
│   │       ├── persona_agent.py
│   │       ├── grading_agent.py
│   │       └── summarization_agent.py
│   ├── pdf_processing/           # PDF processing feature
│   │   ├── __init__.py
│   │   ├── router.py             # FastAPI router
│   │   ├── pipeline.py           # Main orchestrator (extract → analyze → generate)
│   │   ├── parser_service.py     # PDF text extraction (LlamaParse)
│   │   ├── ai_extraction_service.py  # AI analysis (scenario extraction)
│   │   ├── repository.py         # Data access (scenario creation, file storage)
│   │   └── schemas.py            # Request/response models
│   ├── auth/                     # Authentication & authorization
│   │   ├── __init__.py
│   │   ├── router.py             # Login, register, token refresh endpoints
│   │   ├── service.py            # Auth logic (password validation, token management)
│   │   ├── provider.py           # OAuth providers (Google, etc.)
│   │   └── schemas.py            # Auth request/response models
│   ├── professor/                # Professor-specific features
│   │   ├── __init__.py
│   │   ├── router.py             # Professor endpoints
│   │   ├── service.py            # Business logic (cohorts, grading, invitations)
│   │   ├── repository.py         # Data access
│   │   └── schemas.py            # Professor-specific models
│   ├── student/                  # Student-specific features
│   │   ├── __init__.py
│   │   ├── router.py             # Student endpoints
│   │   ├── service.py            # Business logic (simulation instances, progress)
│   │   ├── repository.py         # Data access
│   │   └── schemas.py            # Student-specific models
│   ├── notifications/            # Notification system
│   │   ├── __init__.py
│   │   ├── router.py             # Notification endpoints
│   │   ├── service.py            # Notification logic (email, in-app)
│   │   ├── repository.py         # Data access
│   │   └── templates/            # Email/notification templates
│   └── publishing/               # Publishing feature
│       ├── __init__.py
│       ├── router.py             # Publishing endpoints
│       ├── service.py            # Publishing logic (make simulations available for assignment)
│       ├── repository.py         # Data access
│       └── schemas/              # Publishing schemas
│           ├── __init__.py
│           ├── dto.py            # Pydantic schemas (API request/response models)
│           └── domain.py         # Domain models (dataclasses for internal use)
│
└── tests/                        # Test suite
    ├── __init__.py
    ├── conftest.py               # Pytest configuration, fixtures
    ├── common/                   # Shared test utilities
    │   └── fixtures.py           # Common test fixtures (DB, mocks)
    └── modules/                  # Feature-specific tests
        ├── simulation/
        ├── pdf_processing/
        ├── auth/
        └── ...
```

---

## Detailed Module Explanations

### `app/` - FastAPI Application Framework

**Purpose**: Contains all FastAPI-specific setup and configuration. This is the "wiring" layer that connects everything together.

#### `app/main.py`
- **What it does**: Application entry point that starts the uvicorn server
- **Responsibilities**:
  - Creates FastAPI app instance
  - Registers all routers from `app/routers/`
  - Sets up middleware (CORS, auth, error handling)
  - Configures static file serving
  - Defines health check endpoints
- **Current location**: `backend/main.py`
- **Migration**: Move here, keep minimal logic (delegate to `app.py` factory if needed)

#### `app/dependencies.py`
- **What it does**: FastAPI dependency injection functions
- **Responsibilities**:
  - `get_db()` - Database session provider
  - `get_current_user()` - JWT authentication dependency
  - `get_ai_service()` - AI service provider
  - `require_admin()` - Role-based access control
- **Current location**: Scattered in `utilities/auth.py`, `database/connection.py`
- **Migration**: Consolidate all dependency functions here

#### `app/middleware.py`
- **What it does**: HTTP middleware for request/response processing
- **Responsibilities**:
  - CORS configuration
  - Request logging
  - Error handling (global exception handler)
  - Rate limiting (if not in utils)
- **Current location**: Inline in `main.py`
- **Migration**: Extract middleware logic here

#### `app/routers/`
- **What it does**: Thin wiring layer that imports and includes module routers
- **Responsibilities**:
  - Import routers from `modules/*/router.py`
  - Include them in the main FastAPI app
  - Set route prefixes and tags
  - Handle app-level route concerns (if any)
- **Structure**: Each file is ~10-20 lines, just imports and includes
- **Example**:
  ```python
  # app/routers/simulation.py
  from modules.simulation.router import router
  
  # Include with prefix and tags
  app.include_router(router, prefix="/api/simulation", tags=["Simulation"])
  ```
- **Current location**: `backend/api/*.py` (will be split)
- **Migration**: Create thin wiring files that import from modules

#### `app/lifespan.py`
- **What it does**: Application lifecycle hooks
- **Responsibilities**:
  - Startup: Initialize DB, load AI models, start background tasks
  - Shutdown: Cleanup connections, save state
- **Current location**: Inline in `main.py` using `@asynccontextmanager`
- **Migration**: Extract lifespan logic here

---

### `common/` - Shared Infrastructure

**Purpose**: Contains code used across multiple features. This is the "foundation" that everything else builds on.

#### `common/config.py`
- **What it does**: Centralized configuration management
- **Responsibilities**:
  - Load environment variables
  - Define Pydantic settings models
  - Validate configuration on startup
  - Provide typed access to config values
- **Current location**: `database/connection.py` (settings), `utils/env.py`
- **Migration**: Consolidate all config here using Pydantic Settings

#### `common/logging.py`
- **What it does**: Structured logging setup
- **Responsibilities**:
  - Configure loggers (format, level, handlers)
  - Set up file/console logging
  - Define log context (request IDs, user IDs)
- **Current location**: Scattered, `utilities/debug_logging.py`, `utilities/secure_logging.py`
- **Migration**: Centralize logging configuration here

#### `common/exceptions.py`
- **What it does**: Custom exception classes
- **Responsibilities**:
  - Define domain-specific exceptions (ScenarioNotFound, InvalidGoal, etc.)
  - Provide error codes and messages
  - Enable consistent error handling
- **Current location**: Not explicitly defined (using HTTPException)
- **Migration**: Create custom exception hierarchy

#### `common/db/` - Database Layer

**`common/db/connection.py`**
- **What it does**: SQLAlchemy engine and session management
- **Responsibilities**:
  - Create database engine
  - Provide session factory
  - Handle connection pooling
  - Manage transactions
- **Current location**: `database/connection.py`
- **Migration**: Move here, keep existing functionality

**`common/db/models/`**
- **What it does**: SQLAlchemy ORM models organized by module
- **Structure**: Models are organized in subdirectories by feature module:
  - `models/auth/` - Authentication models (User)
  - `models/publishing/` - Publishing models (Scenario, ScenarioPersona, ScenarioScene, ScenarioReview, ScenarioFile)
  - `models/pdf_processing/` - PDF processing models (future)
  - `models/simulation/` - Simulation models (future)
  - `models/professor/` - Professor models (future)
  - `models/student/` - Student models (future)
  - `models/notifications/` - Notification models (future)
- **Responsibilities**:
  - Define database tables (User, Scenario, ScenarioPersona, etc.)
  - Define relationships (foreign keys, many-to-many)
  - Define table constraints
- **Backward compatibility**: `common/db/models.py` re-exports all models for existing imports
- **Important**: These are SQLAlchemy ORM models (database tables), NOT Pydantic schemas (API DTOs)

**`common/db/schemas.py`**
- **What it does**: Shared Pydantic models for common database entities
- **Responsibilities**:
  - Shared response models (UserResponse, etc.)
  - Common validation rules
- **Note**: Module-specific Pydantic schemas live in `modules/<module>/schemas/`

**`common/db/migrations/`**
- **What it does**: Alembic database migrations
- **Responsibilities**:
  - Version control for database schema
  - Migration scripts (create table, alter column, etc.)
- **Current location**: `database/migrations/`
- **Migration**: Move here, update `alembic.ini` paths

#### `common/services/` - Cross-Cutting Services

**`common/services/email_service.py`**
- **What it does**: Email sending functionality
- **Responsibilities**:
  - Send emails (SMTP, SendGrid, etc.)
  - Template rendering
  - Email queue management
- **Current location**: `services/email_service.py`
- **Migration**: Move here, keep interface simple

**`common/services/cache_service.py`**
- **What it does**: Unified caching interface
- **Responsibilities**:
  - Redis caching (primary)
  - In-memory fallback (if Redis unavailable)
  - Cache key management
  - TTL handling
- **Current location**: `services/ai_cache_service.py`, `services/db_cache_service.py`, `utilities/redis_manager.py`
- **Migration**: Consolidate into single service with adapter pattern

**`common/services/ai_gateway.py`**
- **What it does**: Unified interface for AI services
- **Responsibilities**:
  - OpenAI client wrapper
  - LangChain integration
  - AI service abstraction (can swap providers)
  - Rate limiting, retry logic
- **Current location**: `services/simulation_engine.py`, `langchain_config.py`, scattered OpenAI calls
- **Migration**: Create unified gateway, migrate existing calls

#### `common/utils/` - Helper Utilities

**`common/utils/auth.py`**
- **What it does**: Authentication utilities
- **Responsibilities**:
  - JWT token generation/validation
  - Password hashing/verification
  - Token refresh logic
- **Current location**: `utilities/auth.py`
- **Migration**: Move here, keep existing functions

**`common/utils/security.py`**
- **What it does**: Security-related utilities
- **Responsibilities**:
  - Rate limiting
  - Input validation
  - XSS/CSRF protection helpers
- **Current location**: `utilities/rate_limiter.py`
- **Migration**: Consolidate security utilities here

**`common/utils/id_generator.py`**
- **What it does**: ID generation utilities
- **Responsibilities**:
  - Generate unique IDs
  - UUID helpers
- **Current location**: `utilities/id_generator.py`
- **Migration**: Move here

---

### `modules/` - Feature Modules

**Purpose**: Each module represents a business capability. All code related to that feature lives together, making it easy to understand and modify.

#### Module Structure Pattern

Each module follows this pattern:
- **`router.py`**: FastAPI router with HTTP endpoints (can be split into sub-routers if large)
- **`service.py`**: Business logic (orchestrates operations)
- **`repository.py`**: Data access (database queries)
- **`schemas/`** or **`schemas.py`**: Feature-specific schemas
  - **`dto.py`**: Pydantic schemas (API request/response models)
  - **`domain.py`**: Domain models (dataclasses for internal use)
  - **`schemas.py`**: Alternative single-file approach for simpler modules
- **`tasks.py`**: Background tasks (optional)

**Note on Schemas**: 
- **SQLAlchemy models** (database tables) live in `common/db/models/<module>/`
- **Pydantic schemas** (API DTOs) live in `modules/<module>/schemas/dto.py` or `schemas.py`
- **Domain models** (dataclasses) live in `modules/<module>/schemas/domain.py` if needed

**Router Size Management**: If a module has many endpoints, split the router:
- `router.py` - Main router that includes sub-routers
- `routers/chat.py` - Chat-related endpoints
- `routers/progress.py` - Progress-related endpoints
- `routers/analytics.py` - Analytics endpoints

#### `modules/simulation/` - Simulation Feature

**Purpose**: Handles the core simulation experience (chat with AI personas, goal validation, progress tracking).

**`modules/simulation/router.py`** (or `modules/simulation/routers/` if large)
- **What it does**: HTTP endpoints for simulation
- **Endpoints**:
  - `POST /start` - Start a simulation
  - `POST /linear-chat` - Send chat message
  - `POST /validate-goal` - Validate learning goal
  - `GET /progress` - Get user progress
  - `GET /analytics` - Get simulation analytics
- **Structure**: If >200 lines, split into:
  - `routers/chat.py` - Chat endpoints
  - `routers/progress.py` - Progress/analytics endpoints
  - `routers/validation.py` - Goal validation endpoints
  - `router.py` - Main router that includes sub-routers
- **Current location**: `api/simulation.py`
- **Migration**: Extract route handlers, keep thin (call service methods). Split if needed.

**`modules/simulation/service.py`**
- **What it does**: Simulation business logic
- **Responsibilities**:
  - Orchestrate ChatOrchestrator
  - Validate learning goals
  - Track progress through scenes
  - Generate hints and feedback
  - Coordinate with AI agents
- **Current location**: `api/simulation.py` (inline), `services/simulation_engine.py`
- **Migration**: Extract business logic from router, consolidate engine logic

**`modules/simulation/repository.py`**
- **What it does**: Data access for simulations
- **Responsibilities**:
  - Query scenarios, personas, scenes
  - Save/load user progress
  - Save conversation logs
  - Query simulation analytics
- **Current location**: Inline SQL queries in `api/simulation.py`
- **Migration**: Extract all database queries here

**`modules/simulation/agents/`**
- **What it does**: AI agents for simulation
- **Responsibilities**:
  - `persona_agent.py` - Generate persona responses
  - `grading_agent.py` - Grade student performance
  - `summarization_agent.py` - Summarize conversations
- **Current location**: `agents/persona_agent.py`, `agents/grading_agent.py`, `agents/summarization_agent.py`
- **Migration**: Move here, keep existing functionality

**`modules/simulation/schemas.py`**
- **What it does**: Simulation-specific Pydantic models
- **Models**: `SimulationStartRequest`, `SimulationChatResponse`, `GoalValidationRequest`, etc.
- **Current location**: `database/schemas.py` (mixed with others)
- **Migration**: Extract simulation schemas here

**`modules/simulation/tasks.py`**
- **What it does**: Background tasks
- **Responsibilities**:
  - Cleanup old simulations
  - Generate analytics reports
  - Send progress notifications
- **Current location**: `services/scheduled_cleanup.py`, `services/immediate_cleanup.py`
- **Migration**: Extract simulation-specific cleanup here

#### `modules/pdf_processing/` - PDF Processing Feature

**Purpose**: Handles PDF upload, parsing, and scenario generation from business case studies.

**`modules/pdf_processing/router.py`**
- **What it does**: HTTP endpoints for PDF processing
- **Endpoints**:
  - `POST /api/parse-pdf/upload` - Upload PDF
  - `GET /api/parse-pdf/progress/{session_id}` - Get processing progress
  - `WebSocket /api/parse-pdf/ws/{session_id}` - Real-time progress updates
- **Current location**: `api/parse_pdf.py`, `api/pdf_progress.py`
- **Migration**: Extract route handlers

**`modules/pdf_processing/pipeline.py`**
- **What it does**: Main orchestrator for PDF processing
- **Responsibilities**:
  - Coordinate extraction → analysis → generation
  - Manage processing state
  - Handle errors and retries
- **Current location**: `api/parse_pdf.py` (inline logic)
- **Migration**: Extract pipeline logic here

**`modules/pdf_processing/parser_service.py`**
- **What it does**: PDF text extraction
- **Responsibilities**:
  - Call LlamaParse API
  - Extract text and structure
  - Handle PDF parsing errors
- **Current location**: `api/parse_pdf.py` (inline)
- **Migration**: Extract parsing logic here

**`modules/pdf_processing/ai_extraction_service.py`**
- **What it does**: AI-powered scenario extraction
- **Responsibilities**:
  - Analyze extracted text with GPT-4
  - Extract scenarios, personas, scenes
  - Generate scene images (DALL-E)
- **Current location**: `api/parse_pdf.py` (inline)
- **Migration**: Extract AI analysis logic here

**`modules/pdf_processing/repository.py`**
- **What it does**: Data access for PDF processing
- **Responsibilities**:
  - Save uploaded files
  - Save processing state
  - Create scenarios from extracted data
- **Current location**: Inline queries in `api/parse_pdf.py`
- **Migration**: Extract database operations here

#### `modules/auth/` - Authentication Feature

**Purpose**: Handles user authentication and authorization.

**`modules/auth/router.py`**
- **What it does**: Auth endpoints
- **Endpoints**:
  - `POST /api/auth/register` - User registration
  - `POST /api/auth/login` - User login
  - `POST /api/auth/refresh` - Token refresh
  - `POST /api/auth/logout` - User logout
- **Current location**: `main.py` (inline), `api/oauth.py`
- **Migration**: Extract auth routes here

**`modules/auth/service.py`**
- **What it does**: Authentication business logic
- **Responsibilities**:
  - Validate credentials
  - Generate JWT tokens
  - Manage sessions
  - Handle password reset
- **Current location**: `utilities/auth.py` (functions)
- **Migration**: Convert to service class, consolidate logic

**`modules/auth/provider.py`**
- **What it does**: OAuth provider integrations
- **Responsibilities**:
  - Google OAuth
  - Other OAuth providers (future)
- **Current location**: `api/oauth.py`, `utilities/oauth.py`
- **Migration**: Extract OAuth logic here

#### `modules/professor/` - Professor Features

**Purpose**: Professor-specific functionality (cohorts, grading, invitations).

**`modules/professor/router.py`**
- **What it does**: Professor endpoints
- **Endpoints**:
  - `GET /api/professor/cohorts` - List cohorts
  - `POST /api/professor/cohorts` - Create cohort
  - `POST /api/professor/invitations` - Send invitations
  - `GET /api/professor/grading` - Get grading materials
- **Current location**: `api/professor/*.py`
- **Migration**: Consolidate professor routes here

**`modules/professor/service.py`**
- **What it does**: Professor business logic
- **Responsibilities**:
  - Manage cohorts
  - Handle invitations
  - Process grading
  - Manage notifications
- **Current location**: Inline in `api/professor/*.py`
- **Migration**: Extract business logic here

#### `modules/student/` - Student Features

**Purpose**: Student-specific functionality (simulation instances, progress).

**`modules/student/router.py`**
- **What it does**: Student endpoints
- **Endpoints**:
  - `GET /api/student/simulation-instances` - List simulations
  - `POST /api/student/simulation-instances` - Start simulation
  - `GET /api/student/cohorts` - List enrolled cohorts
- **Current location**: `api/student/*.py`
- **Migration**: Consolidate student routes here

**`modules/student/service.py`**
- **What it does**: Student business logic
- **Responsibilities**:
  - Manage simulation instances
  - Track progress
  - Handle notifications
- **Current location**: Inline in `api/student/*.py`
- **Migration**: Extract business logic here

#### `modules/notifications/` - Notification System

**Purpose**: Handles all notifications (email, in-app).

**`modules/notifications/router.py`**
- **What it does**: Notification endpoints
- **Endpoints**:
  - `GET /api/notifications` - List notifications
  - `POST /api/notifications/mark-read` - Mark as read
- **Current location**: `api/professor/notifications.py`, `api/student/notifications.py`
- **Migration**: Consolidate notification routes here

**`modules/notifications/service.py`**
- **What it does**: Notification business logic
- **Responsibilities**:
  - Send notifications (email, in-app)
  - Manage notification preferences
  - Queue notifications
- **Current location**: `services/notification_service.py`
- **Migration**: Move here, enhance with templates

#### `modules/publishing/` - Publishing Feature

**Purpose**: Handles publishing of simulations generated from the simulation builder so they can be assigned to students. Publishing makes a simulation available for assignment by changing its status from draft to published.

**`modules/publishing/router.py`**
- **What it does**: Publishing endpoints for simulations
- **Endpoints**:
  - `GET /api/publishing/simulations/` - Get user's simulations
  - `GET /api/publishing/simulations/drafts/` - Get draft simulations
  - `POST /api/publishing/simulations/publish/{scenario_id}` - Publish a simulation (makes it available for assignment)
  - `POST /api/publishing/simulations/save` - Save simulation changes
  - `GET /api/publishing/simulations/{scenario_id}/full` - Get full simulation details
- **Note**: The API uses "simulations" terminology, but database models use "Scenario" table name
- **Current location**: `api/publishing.py`
- **Migration**: Extract routes here

**`modules/publishing/service.py`**
- **What it does**: Publishing business logic for simulations
- **Responsibilities**:
  - Handle publishing workflow (change simulation status from draft to published)
  - Update simulation flags (`is_draft = False`, `is_public = True`, `status = "active"`)
  - Store publishing metadata (category, difficulty level, tags, estimated duration)
  - Validate simulation is ready for publishing
- **Current location**: Inline in `api/publishing.py`
- **Migration**: Extract business logic here

**`modules/publishing/schemas/`**
- **`dto.py`**: Pydantic schemas for API request/response models
  - `ScenarioPublishRequest` - Request model for publishing a simulation
  - `ScenarioPublishingResponse` - Response model with simulation data
  - `PublishResponse`, `SaveResponse`, `StatusUpdateRequest` - Publishing operation responses
  - `CloneResponse` - Response for cloning simulations
  - `CleanupStatsResponse` - Response for cleanup statistics
- **`domain.py`**: Domain models (dataclasses) for internal use
  - `PDFMetadata` - Metadata for PDF file storage
  - `ImageUploadInfo` - Information for image uploads
- **Note**: SQLAlchemy models (Scenario, ScenarioFile) are in `common/db/models/publishing/`. Note: The database uses "Scenario" as the table name, but the API layer refers to them as "simulations".

---

### `tests/` - Test Suite

**Purpose**: Comprehensive test coverage following the same structure as production code.

**`tests/conftest.py`**
- **What it does**: Pytest configuration and shared fixtures
- **Responsibilities**:
  - Configure pytest
  - Define database fixtures (test DB, sessions)
  - Define mock fixtures (AI services, external APIs)
- **Current location**: Not present (needs creation)
- **Migration**: Create comprehensive test setup

**`tests/common/fixtures.py`**
- **What it does**: Shared test utilities
- **Responsibilities**:
  - Common fixtures (users, scenarios)
  - Test data factories
  - Mock helpers
- **Current location**: Not present
- **Migration**: Create reusable test utilities

**`tests/modules/`**
- **What it does**: Feature-specific tests
- **Structure**: Mirrors `modules/` structure
- **Responsibilities**:
  - Unit tests for services
  - Integration tests for routers
  - Repository tests
- **Current location**: Not present (needs creation)
- **Migration**: Create test suite as features are migrated

---

## Data Flow Example

### Starting a Simulation

```
1. HTTP Request → app/routers/simulation.py (wiring layer, ~5 lines)
   ↓
2. Routes to → modules/simulation/router.py (actual endpoints)
   ↓
3. Router validates request schema → modules/simulation/schemas.py
   ↓
4. Router calls service → modules/simulation/service.py
   ↓
5. Service queries data → modules/simulation/repository.py
   ↓
6. Repository uses DB session → common/db/connection.py
   ↓
7. Service orchestrates AI → modules/simulation/agents/persona_agent.py
   ↓
8. Agent uses AI gateway → common/services/ai_gateway.py
   ↓
9. Service returns result → Router → HTTP Response
```


---

## Benefits of This Architecture

1. **Easier Navigation**: Find all simulation code in `modules/simulation/`
2. **Faster Development**: Less indirection, clearer dependencies
3. **Better Testing**: Each module can be tested in isolation
4. **Incremental Migration**: Can migrate one feature at a time
5. **Clear Boundaries**: Each module owns its domain
6. **Shared Infrastructure**: Common code lives in one place
7. **Scalable**: Easy to add new features (new module)

---

## Key Principles

1. **Routers are thin**: They validate requests and call services
2. **Services contain business logic**: They orchestrate operations
3. **Repositories handle data access**: They abstract database queries
4. **Common code is shared**: Infrastructure lives in `common/`
5. **Modules are independent**: Each feature is self-contained
6. **Tests mirror structure**: Same organization as production code

---

## Questions & Decisions

### Should routers be in `app/routers/` or `modules/*/router.py`?
**Decision**: Routers live in `modules/*/router.py` (feature-owned). `app/routers/` is just a thin wiring layer (~10-20 lines per file) that imports and includes module routers. This keeps business logic with features while maintaining a clean app structure.

### What if a module router gets too large?
**Decision**: Split into sub-routers within the module:
- `modules/simulation/routers/chat.py`
- `modules/simulation/routers/progress.py`
- `modules/simulation/router.py` (includes sub-routers)

This keeps related endpoints together while preventing huge files.

**Example Structure for Large Module**:
```
modules/simulation/
├── router.py              # Main router (~20 lines)
│   from .routers import chat_router, progress_router, validation_router
│   router = APIRouter()
│   router.include_router(chat_router)
│   router.include_router(progress_router)
│   router.include_router(validation_router)
├── routers/
│   ├── chat.py           # Chat endpoints (~100 lines)
│   ├── progress.py       # Progress/analytics (~80 lines)
│   └── validation.py     # Goal validation (~60 lines)
├── service.py
└── ...
```

### Should we use repositories or direct DB access in services?
**Decision**: Use repositories. They abstract database queries and make testing easier.

### Should schemas be in `common/db/schemas.py` or `modules/*/schemas.py`?
**Decision**: Both. Shared schemas (User, Scenario) in `common/db/schemas.py`, feature-specific schemas in modules.

### Should AI agents be in modules or common?
**Decision**: In modules. Agents are feature-specific (simulation agents vs PDF agents).

---

## Development Guidelines & Principles

### File Size & Complexity

**File Size Limits**:
- **Target**: Keep files under 300 lines
- **Warning**: Files over 400 lines should be refactored
- **Action**: Split large files by responsibility (e.g., split service into multiple focused services)

**Function/Method Size**:
- **Target**: Functions under 50 lines
- **Warning**: Functions over 100 lines should be broken down
- **Action**: Extract helper functions or move logic to service classes

**Class Size**:
- **Target**: Classes under 500 lines
- **Warning**: Classes over 800 lines likely violate Single Responsibility Principle
- **Action**: Split into multiple classes or use composition

**Cyclomatic Complexity**:
- **Target**: Functions with complexity < 10
- **Warning**: Complexity > 15 indicates need for refactoring
- **Action**: Break into smaller, testable functions

### Code Organization

**Single Responsibility Principle**:
- Each file/class/function should have one clear purpose
- If you can't describe what a function does in one sentence, it's too complex
- Example: `simulation_service.py` handles simulation logic, not database queries (use repository)

**Separation of Concerns**:
- **Routers**: HTTP concerns only (validation, status codes, headers)
- **Services**: Business logic only (orchestration, validation, transformation)
- **Repositories**: Data access only (queries, transactions)
- **Schemas**: Data validation and serialization only

**Dependency Direction**:
- Modules should not import from each other (avoid circular dependencies)
- Dependencies flow: `app` → `modules` → `common`
- Services can use repositories, but repositories should not use services
- Common utilities should have no dependencies on modules

### Naming Conventions

**Files & Modules**:
- Use `snake_case` for all file names: `simulation_service.py`, `user_repository.py`
- Module names should be singular: `modules/simulation/` not `modules/simulations/`
- Router files: `router.py` (in modules) or descriptive names in `app/routers/`

**Classes**:
- Use `PascalCase`: `SimulationService`, `UserRepository`, `ChatOrchestrator`
- Service classes end with `Service`: `SimulationService`, `EmailService`
- Repository classes end with `Repository`: `ScenarioRepository`, `UserRepository`
- Exception classes end with `Error` or `Exception`: `ScenarioNotFoundError`, `ValidationError`

**Functions & Variables**:
- Use `snake_case`: `get_user_by_id()`, `validate_goal()`, `process_pdf()`
- Function names should be verbs: `create_scenario()`, not `scenario_creator()`
- Boolean variables/functions: `is_active`, `has_permission()`, `can_edit()`

**Constants**:
- Use `UPPER_SNAKE_CASE`: `MAX_RETRY_ATTEMPTS`, `DEFAULT_TIMEOUT`, `API_BASE_URL`

**Database Models**:
- Use `PascalCase` singular: `User`, `Scenario`, `ScenarioPersona`
- Table names follow SQLAlchemy conventions (usually plural, lowercase)

### Import Organization

**Import Order** (enforced by formatter):
1. Standard library imports
2. Third-party imports (FastAPI, SQLAlchemy, etc.)
3. Local application imports (from `common`, `modules`)

**Example**:
```python
# Standard library
from typing import List, Optional
from datetime import datetime

# Third-party
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

# Local
from common.db.connection import get_db
from modules.simulation.service import SimulationService
from modules.simulation.schemas import SimulationStartRequest
```

**Import Style**:
- Use absolute imports: `from modules.simulation.service import SimulationService`
- Avoid relative imports except within same module: `from .schemas import SimulationSchema`
- Group related imports together

### Error Handling

**Exception Hierarchy**:
- Create custom exceptions in `common/exceptions.py`
- Inherit from appropriate base exceptions
- Example:
  ```python
  class DomainError(Exception):
      """Base exception for domain errors"""
      pass

  class ScenarioNotFoundError(DomainError):
      """Raised when scenario is not found"""
      pass

  class InvalidGoalError(DomainError):
      """Raised when goal validation fails"""
      pass
  ```

**Error Handling Pattern**:
- Services raise domain exceptions
- Routers catch exceptions and convert to HTTP responses
- Use HTTPException for HTTP-specific errors (400, 401, 403, 404, etc.)
- Log errors with appropriate context (user ID, request ID, etc.)

**Example**:
```python
# In service
if not scenario:
    raise ScenarioNotFoundError(f"Scenario {scenario_id} not found")

# In router
try:
    result = service.start_simulation(request)
except ScenarioNotFoundError as e:
    raise HTTPException(status_code=404, detail=str(e))
```

### Testing Requirements



**Test Organization**:
- Mirror production structure: `tests/modules/simulation/test_service.py`
- One test file per production file: `service.py` → `test_service.py`
- Group related tests in classes: `TestSimulationService`, `TestGoalValidation`

**Test Types**:
- **Unit tests**: Test individual functions/classes in isolation
- **Integration tests**: Test module interactions (service + repository)
- **API tests**: Test HTTP endpoints end-to-end

**Test Naming**:
- Use descriptive names: `test_start_simulation_creates_progress_record()`
- Follow pattern: `test_<function>_<condition>_<expected_result>()`

**Fixtures**:
- Use pytest fixtures for common setup (DB sessions, test users)
- Place shared fixtures in `tests/common/fixtures.py`
- Module-specific fixtures in `tests/modules/<module>/conftest.py`

### Documentation Standards

**Docstrings**:
- All public functions, classes, and modules should have docstrings
- Use Google-style docstrings:
  ```python
  def start_simulation(
      self, 
      scenario_id: int, 
      user_id: int
  ) -> SimulationInstance:
      """Start a new simulation instance for a user.
      
      Args:
          scenario_id: ID of the scenario to start
          user_id: ID of the user starting the simulation
          
      Returns:
          SimulationInstance: The created simulation instance
          
      Raises:
          ScenarioNotFoundError: If scenario doesn't exist
          ValidationError: If user cannot start simulation
      """
  ```

**Type Hints**:
- Use type hints for all function parameters and return values
- Use `Optional[T]` for nullable values, not `T | None` (Python 3.10+)
- Use `List[T]`, `Dict[K, V]` from `typing` module

**Comments**:
- Code should be self-documenting (clear names, simple logic)
- Comments explain "why", not "what"
- Remove commented-out code (use git history instead)

### Performance Guidelines

**Database Queries**:
- Use eager loading (`selectinload`, `joinedload`) to avoid N+1 queries
- Limit result sets with pagination (default: 20 items per page)
- Use database indexes for frequently queried fields
- Avoid loading entire tables into memory

**Caching**:
- Cache expensive operations (AI calls, complex calculations)
- Use Redis for shared cache, in-memory for request-scoped cache
- Set appropriate TTLs (Time To Live) for cached data
- Invalidate cache on data updates

**Async Operations**:
- Use `async/await` for I/O-bound operations (DB, API calls, file operations)
- Use background tasks for long-running operations (email sending, PDF processing)
- Don't use async for CPU-bound operations (use ThreadPoolExecutor instead)

**API Response Times**:
- **Target**: < 200ms for simple endpoints
- **Acceptable**: < 500ms for complex operations
- **Warning**: > 1s requires optimization or background processing

### Security Practices

**Authentication & Authorization**:
- Always validate JWT tokens in dependencies
- Use role-based access control (RBAC) for permissions
- Never trust client input - validate on server
- Use `get_current_user` dependency for protected routes

**Input Validation**:
- Validate all user input using Pydantic schemas
- Sanitize user input before database queries (prevent SQL injection)
- Validate file uploads (type, size, content)
- Use parameterized queries (SQLAlchemy handles this)

**Sensitive Data**:
- Never log passwords, tokens, or sensitive user data
- Use environment variables for secrets (never commit to git)
- Hash passwords using bcrypt (never store plaintext)
- Use HTTPS for all API communication

**Rate Limiting**:
- Implement rate limiting for authentication endpoints
- Use different limits for different user roles
- Log and monitor rate limit violations

### Dependency Management

**Dependencies**:
- Use [uv](https://github.com/astral-sh/uv) for dependency management and installation
- Pin exact versions in `requirements.lock` for production
- Use `requirements.in` (main), `requirements-dev.in` (dev/test) as input files
- Run `uv pip compile` to update lock files
- Regularly check and update dependencies for security patches via `uv pip compile --upgrade`
- Review and approve new dependencies before adding to `requirements.in`

**Dependency Injection**:
- Use FastAPI’s dependency injection system
- Avoid global state – pass dependencies explicitly as parameters
- Make services easily testable by accepting dependencies in `__init__`

**Circular Dependencies**:
- Avoid circular imports between modules
- If necessary, use type hints with `from __future__ import annotations`
- Refactor aggressively if circular dependencies arise


### Code Review Guidelines

**PR Requirements**:
- Keep PRs focused (one feature/fix per PR)
- Include tests for new functionality
- Update architecture docs if structure changes
- No approval needed for Dev and Staging Branch but at least one approval needed for Prod
- Always open A PR with your change to all three branchen Dev/Stag/Prod
**Code Review Checklist**:

- TBD in corperation with CodeRabbit

### Refactoring Guidelines

**When to Refactor**:
- File exceeds 400 lines
- Function exceeds 100 lines
- Cyclomatic complexity > 15
- Code duplication appears (DRY principle)
- Tests become difficult to write

**Refactoring Process**:
1. Write tests for existing behavior
2. Refactor incrementally (small changes)
3. Run tests after each change
4. Commit frequently with clear messages
5. Review changes before merging

**Common Refactoring Patterns**:
- Extract function: Break large function into smaller ones
- Extract class: Move related functions into a class
- Move method: Move method to more appropriate class
- Split module: Break large file into multiple files

### Performance Monitoring

**Metrics to Track**:
- API response times (p50, p95, p99)
- Database query performance
- Error rates by endpoint
- Cache hit rates
- Background task completion times

**Logging**:
- Log all errors with full context
- Use structured logging (JSON format)
- Include request IDs for tracing
- Log performance metrics for slow operations

