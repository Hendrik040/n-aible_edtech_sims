# Architecture Update Summary

## Overview

This document summarizes the major architecture updates to the AI Agent Education Platform, reflecting the transition to a modular, feature-based backend architecture.

## What Changed

### 1. Documentation Updates

#### New Documents Created
- **`docs/Quick_Reference.md`** - Quick lookup guide with sequence diagrams and common patterns
- **`docs/architecture/architecture-diagram.md`** - Comprehensive visual architecture with Mermaid diagrams
- **`docs/architecture/system-overview.md`** - Detailed explanation of the modular architecture
- **`docs/architecture/modular-migration-guide.md`** - Migration tracking and development patterns

#### Updated Documents
- **`README.md`** - Updated architecture section with modular design explanation
- **`docs/README.md`** - Added links to new architecture documentation

### 2. Architecture Improvements

#### Modular Backend Structure
```
backend/
├── app/                    # FastAPI wiring layer
│   ├── main.py            # Application entry point
│   ├── dependencies.py    # Dependency injection
│   └── middleware.py      # CORS, auth, logging
│
├── common/                # Shared infrastructure  
│   ├── config.py          # Pydantic settings
│   ├── db/                # Database layer
│   │   ├── base.py        # SQLAlchemy Base
│   │   ├── core.py        # Engine & sessions
│   │   └── models/        # Shared ORM models
│   └── utils/             # Helper utilities
│
├── modules/               # Feature modules
│   ├── simulation/        # ✅ Partial (needs service/repo)
│   ├── pdf_processing/    # ✅ Complete
│   ├── auth/              # ✅ Complete
│   ├── professor/         # ✅ Complete
│   ├── student/           # ✅ Complete
│   ├── notifications/     # 🔄 In progress
│   └── publishing/        # ⏳ Pending
│
└── agents/               # AI agents
    ├── persona_agent.py
    ├── grading_agent.py
    └── summarization_agent.py
```

#### Key Architectural Principles
1. **One-way dependencies**: `app` → `modules` → `common`
2. **Repository pattern**: Clean separation of data access
3. **Service layer**: Business logic orchestration
4. **Feature modules**: Self-contained with router, service, repository, schemas

### 3. Visual Documentation

#### New Sequence Diagrams

**PDF-to-Simulation Pipeline**
- Shows complete flow from PDF upload through AI extraction to database storage
- Includes LlamaParse, OpenAI GPT-4, and DALL-E 3 interactions

**Simulation Execution Flow**
- Demonstrates student chat interaction with AI personas
- Shows caching strategy and database operations
- Includes progress tracking and scene completion logic

**Authentication Flow**
- Google OAuth complete sequence
- Email/password authentication flow
- JWT token generation and cookie management

#### Architecture Diagrams

**High-Level System Architecture**
- Frontend → API Gateway → Modules → External Services
- Shows all major components and their relationships

**Backend Modular Architecture**
- Detailed view of the modular structure
- Dependency flow visualization
- Module pattern explanation

**Database Schema**
- Entity-relationship diagram with all tables
- Shows relationships and key fields
- Includes new features (cohorts, notifications, invitations)

**Caching Architecture**
- Redis caching strategy
- Cache types and TTL configuration
- Cache invalidation flow

**Security Architecture**
- Authentication layers (JWT, OAuth, cookies)
- Authorization (RBAC, ownership checks)
- Data protection mechanisms

**Deployment Architecture**
- Development, staging, and production environments
- Shows Railway deployment structure

### 4. Migration Status

#### Completed Migrations ✅
- `common/config.py` - Pydantic settings
- `common/db/base.py` - SQLAlchemy Base
- `common/db/core.py` - Database engine and sessions
- `common/db/models/user.py` - User model
- `common/db/models/cache.py` - Cache model
- `common/db/models/notifications.py` - Notification model
- `modules/pdf_processing/` - Complete module with all components
- `modules/auth/` - Authentication with OAuth
- `modules/professor/` - Professor features with sub-routers
- `modules/student/` - Student features with sub-routers

#### In Progress 🔄
- `modules/simulation/` - Router exists, needs service/repository
- Database models migration to modular structure
- Legacy services migration to `common/services/`

#### Pending ⏳
- `modules/publishing/` - Marketplace features
- `modules/notifications/` - Full notification system
- Test suite expansion
- Remaining database models

## Key Features Documented

### 1. PDF Processing Pipeline
- LlamaParse integration for text extraction
- OpenAI GPT-4 for metadata and persona extraction
- DALL-E 3 for scene image generation
- WebSocket progress tracking
- Repository pattern for data persistence

### 2. Simulation System
- Multi-scene progression with goals
- AI persona interactions with personality traits
- ChatOrchestrator integration
- Progress tracking and conversation logging
- Caching for performance optimization

### 3. Authentication System
- Google OAuth with state management
- Email/password authentication
- JWT tokens with HttpOnly cookies
- Role-based access control (RBAC)
- Secure session management

### 4. Cohort Management
- Professor-created learning groups
- Student invitation system with tokens
- Cohort-based simulation assignments
- Progress tracking per cohort
- Notification integration

### 5. Caching Strategy
- Redis-backed caching
- AI response cache (1 hour TTL)
- Database query cache (5 min TTL)
- Session cache (30 min TTL)
- Scenario data cache (15 min TTL)

## Development Patterns

### Module Structure Pattern
```python
modules/<feature>/
├── router.py          # HTTP endpoints
├── service.py         # Business logic
├── repository.py      # Data access
└── schemas/           # Pydantic models
```

### Dependency Injection Pattern
```python
@router.post("/start")
async def start_simulation(
    request: SimulationStartRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    repository = SimulationRepository(db)
    service = SimulationService(repository)
    return await service.start_simulation(request, current_user.id)
```

### Error Handling Pattern
```python
# Service raises domain exceptions
if not scenario:
    raise KeyError(scenario_id)

# Router converts to HTTP exceptions
try:
    result = service.start_simulation(...)
except KeyError as e:
    raise HTTPException(404, f"Scenario {e} not found")
```

## Performance Optimizations

1. **Redis Caching** - Frequently accessed data cached with appropriate TTLs
2. **Connection Pooling** - PostgreSQL pool (70 connections, 80 max overflow)
3. **Async Processing** - FastAPI async endpoints for I/O operations
4. **Eager Loading** - Avoid N+1 queries with SQLAlchemy eager loading
5. **WebSocket Updates** - Real-time progress for long-running operations

## Security Improvements

1. **JWT with HttpOnly Cookies** - No JavaScript access to tokens
2. **OAuth State Management** - CSRF protection for OAuth flows
3. **Password Hashing** - bcrypt for secure password storage
4. **Input Validation** - Pydantic schemas validate all inputs
5. **RBAC** - Role-based access control for endpoints
6. **Rate Limiting** - Protect authentication endpoints

## Technology Stack

### Backend
- **FastAPI** - Modern async web framework
- **Python 3.11+** - With type hints and async support
- **SQLAlchemy 2.0** - Modern ORM with async support
- **Pydantic 2.0** - Data validation and settings
- **Alembic** - Database migration management
- **Redis** - Caching and session storage
- **uv** - Fast Python package manager

### AI/ML
- **OpenAI GPT-4** - Language model for personas and content
- **LlamaParse** - PDF parsing and extraction
- **DALL-E 3** - Image generation for scenes
- **LangChain** - AI agent framework (being phased out)

### Frontend
- **Next.js 15** - React framework with App Router
- **TypeScript** - Type safety
- **Tailwind CSS** - Utility-first styling
- **shadcn/ui** - Component library

### Infrastructure
- **PostgreSQL 14+** - Primary database
- **Redis 6+** - Caching layer
- **Railway** - Cloud deployment
- **Docker** - Local development

## Quick Reference

### Common Commands
```bash
# Backend (from backend/)
uvicorn app.main:app --reload

# Frontend (from frontend/)
npm run dev

# Database migrations (from backend/database/)
alembic upgrade head
alembic revision --autogenerate -m "message"

# Docker services
docker-compose up -d
docker-compose down
```

### Key Endpoints
```
POST /api/parse-pdf/upload              # Upload PDF
POST /api/simulation/start              # Start simulation
POST /api/simulation/linear-chat        # Chat with personas
POST /users/login                       # Login
GET  /api/auth/google                   # Google OAuth
GET  /api/professor/cohorts             # List cohorts
GET  /api/student/simulation-instances  # List simulations
```

### Environment Variables
```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/dbname
OPENAI_API_KEY=sk-...
REDIS_URL=redis://localhost:6379
SECRET_KEY=your-secret-key
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

## Next Steps

### Immediate (Week 1-2)
1. Complete `modules/simulation/` migration (service + repository)
2. Extract remaining database models to modular structure
3. Write comprehensive test suite
4. Update API documentation with new endpoints

### Short-term (Month 1)
1. Complete `modules/publishing/` migration
2. Consolidate notification system
3. Migrate legacy services to `common/services/`
4. Performance benchmarking and optimization

### Mid-term (Quarter 1 2025)
1. GraphQL API implementation
2. Real-time collaboration features
3. Advanced analytics dashboard
4. Mobile app development

## Resources

### Documentation
- [Quick Reference](docs/Quick_Reference.md)
- [System Overview](docs/architecture/system-overview.md)
- [Architecture Diagrams](docs/architecture/architecture-diagram.md)
- [Migration Guide](docs/architecture/modular-migration-guide.md)

### External Resources
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 Docs](https://docs.sqlalchemy.org/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Next.js Documentation](https://nextjs.org/docs)

## Summary

The platform has successfully transitioned to a **modular, feature-based architecture** that:

- ✅ Improves code organization with clear module boundaries
- ✅ Reduces coupling through one-way dependencies
- ✅ Enhances testability with repository pattern
- ✅ Enables scalability through independent modules
- ✅ Maintains high performance with caching and async processing
- ✅ Ensures security with JWT, OAuth, and RBAC

The documentation now provides comprehensive visual representations, detailed explanations, and practical examples for developers to understand and extend the platform effectively.

---

**Last Updated**: November 24, 2024
**Architecture Version**: 2.0
**Status**: In Active Migration

