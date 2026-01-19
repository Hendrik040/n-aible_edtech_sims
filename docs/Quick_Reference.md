# Quick Reference Guide

## Platform Overview

The **AI Agent Education Platform** transforms business case studies into immersive AI-powered simulations using a modular, feature-based architecture.

## Core Flows

### 1. PDF to Simulation

```mermaid
sequenceDiagram
    participant Prof as Professor
    participant FE as Frontend
    participant API as API Gateway
    participant PDF as pdf_processing
    participant LP as LlamaParse
    participant GPT as OpenAI
    participant DB as Database

    Prof->>FE: Upload PDF
    FE->>API: POST /api/parse-pdf/upload
    API->>PDF: Process PDF
    PDF->>LP: Extract text
    LP-->>PDF: Structured content
    PDF->>GPT: Extract metadata & personas
    GPT-->>PDF: Scenario data
    PDF->>GPT: Generate scenes
    GPT-->>PDF: Scene descriptions
    PDF->>GPT: Create images (DALL-E)
    GPT-->>PDF: Image URLs
    PDF->>DB: Save scenario
    DB-->>PDF: Scenario ID
    PDF-->>API: Success
    API-->>FE: Scenario ready
    FE-->>Prof: Preview
```

### 2. Student Simulation

```mermaid
sequenceDiagram
    participant S as Student
    participant FE as Frontend
    participant API as API Gateway
    participant Sim as simulation
    participant Agent as PersonaAgent
    participant GPT as OpenAI
    participant DB as Database

    S->>FE: Start simulation
    FE->>API: POST /api/simulation/start
    API->>Sim: start_simulation()
    Sim->>DB: Load scenario + create progress
    DB-->>Sim: Data
    Sim-->>API: Success
    API-->>FE: Ready
    
    loop Chat
        S->>FE: Send message
        FE->>API: POST /api/simulation/linear-chat
        API->>Sim: process_message()
        Sim->>DB: Get history
        Sim->>Agent: generate_response()
        Agent->>GPT: AI call
        GPT-->>Agent: Response
        Sim->>DB: Save conversation
        Sim-->>API: Message
        API-->>FE: Display
    end
```

### 3. Authentication (OAuth)

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant API as API Gateway
    participant Auth as auth module
    participant Google as Google OAuth
    participant DB as Database

    U->>FE: Login with Google
    FE->>API: GET /api/auth/google
    API->>Auth: initiate_oauth()
    Auth->>Google: Auth request
    Google-->>U: Login page
    U->>Google: Authenticate
    Google->>API: Callback + code
    API->>Auth: handle_callback()
    Auth->>Google: Exchange code
    Google-->>Auth: User info
    Auth->>DB: Find/create user
    Auth->>Auth: Create JWT
    Auth-->>API: Set cookie
    API-->>FE: Redirect
```

## Architecture Layers

### Backend Structure

```
backend/
├── app/                    # FastAPI wiring
│   ├── main.py            # Entry point
│   ├── dependencies.py    # DI providers
│   └── middleware.py      # CORS, auth
│
├── modules/               # Feature modules
│   ├── simulation/
│   ├── pdf_processing/
│   ├── auth/
│   ├── professor/
│   └── student/
│
├── common/                # Shared infrastructure
│   ├── config.py         # Settings
│   ├── db/               # Database
│   └── utils/            # Helpers
│
└── agents/               # AI agents
    ├── persona_agent.py
    ├── grading_agent.py
    └── summarization_agent.py
```

### Dependency Flow

```
app/ → modules/ → common/
           ↓
        agents/ → External APIs
```

### Module Pattern

```
modules/<feature>/
├── router.py         # HTTP endpoints
├── service.py        # Business logic
├── repository.py     # Data access
└── schemas/          # Pydantic models
```

## Key Endpoints

### Authentication
```
POST   /users/register             # Register new user
POST   /users/login                # Login (email/password)
GET    /api/auth/google            # Google OAuth
GET    /api/auth/google/callback   # OAuth callback
POST   /users/logout               # Logout
GET    /users/me                   # Current user
```

### PDF Processing
```
POST   /api/parse-pdf/upload       # Upload PDF
GET    /api/parse-pdf/progress/{session_id}  # Progress
WS     /ws/pdf-progress/{session_id}         # WebSocket updates
```

### Simulation
```
POST   /api/simulation/start       # Start simulation
POST   /api/simulation/linear-chat # Send message
GET    /api/simulation/progress    # Get progress
```

### Professor
```
GET    /api/professor/cohorts      # List cohorts
POST   /api/professor/cohorts      # Create cohort
POST   /api/professor/invitations  # Send invitations
GET    /api/professor/grading      # Get grading materials
```

### Student
```
GET    /api/student/simulation-instances  # List simulations
POST   /api/student/simulation-instances  # Start simulation
GET    /api/student/cohorts                # List cohorts
```

### Scenarios
```
GET    /api/scenarios/             # List user scenarios
GET    /api/scenarios/drafts       # List drafts
GET    /api/scenarios/{id}         # Get scenario details
DELETE /api/scenarios/{id}         # Delete scenario
```

## Database Schema (Core Tables)

```sql
-- Users
users (id, user_id, email, role, password_hash, ...)

-- Scenarios
scenarios (id, unique_id, title, description, created_by, ...)

-- Personas
scenario_personas (id, scenario_id, name, role, personality_traits, ...)

-- Scenes
scenario_scenes (id, scenario_id, title, description, scene_order, ...)

-- Progress
user_progress (id, user_id, scenario_id, current_scene_id, status, ...)

-- Conversations
conversation_logs (id, user_progress_id, scene_id, message_content, ...)

-- Cohorts
cohorts (id, name, professor_id, scenario_id, ...)
cohort_memberships (id, cohort_id, student_id, status, ...)
cohort_invitations (id, cohort_id, email, invitation_token, ...)

-- Notifications
notifications (id, user_id, type, message, is_read, ...)
```

## Environment Variables

### Required
```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname
OPENAI_API_KEY=sk-...
SECRET_KEY=your-secret-key-32-chars-minimum
```

### Optional
```bash
REDIS_URL=redis://localhost:6379
ANTHROPIC_API_KEY=sk-...
LLAMAPARSE_API_KEY=llx-...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:3000/auth/google/callback
```

### AWS/Wasabi (File Storage)
```bash
# AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_BUCKET_NAME=...
AWS_REGION=us-east-1

# OR Wasabi
WASABI_ACCESS_KEY_ID=...
WASABI_SECRET_ACCESS_KEY=...
WASABI_BUCKET_NAME=...
WASABI_ENDPOINT_URL=https://s3.wasabisys.com
```

## Common Commands

### Development
```bash
# Backend
cd backend
source venv/bin/activate  # Activate venv
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm run dev  # or pnpm dev

# Database
cd backend/database
alembic upgrade head  # Run migrations
alembic revision --autogenerate -m "message"  # Create migration
```

### Docker
```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f postgres redis

# Stop services
docker-compose down

# Reset database
docker-compose down -v  # Removes volumes
docker-compose up -d
```

### Testing
```bash
# Run all tests
pytest

# Run specific module
pytest tests/modules/simulation/

# Run with coverage
pytest --cov=modules --cov-report=html
```

## Cache Keys

### AI Response Cache (TTL: 1 hour)
```
ai_cache:{hash}
```

### Database Query Cache (TTL: 5 min)
```
db_cache:scenarios:{user_id}
db_cache:scenario:{scenario_id}
```

### Session Cache (TTL: 30 min)
```
session:{user_id}
```

## Error Codes

```python
400  # Bad Request - Invalid input
401  # Unauthorized - No/invalid token
403  # Forbidden - No permission
404  # Not Found - Resource doesn't exist
409  # Conflict - Duplicate resource
422  # Unprocessable Entity - Validation failed
500  # Internal Server Error - Server issue
```

## Performance Tips

1. **Use caching** - Redis caches AI responses and DB queries
2. **Eager load relationships** - Avoid N+1 queries
3. **Pagination** - Don't load all records at once
4. **Async processing** - Use FastAPI's async for I/O operations
5. **Connection pooling** - Already configured (70 connections)

## Security Checklist

- ✅ JWT tokens with 30-min expiry
- ✅ HttpOnly cookies (no JavaScript access)
- ✅ Password hashing with bcrypt
- ✅ Input validation with Pydantic
- ✅ SQL injection prevention (SQLAlchemy ORM)
- ✅ CORS policy enforcement
- ✅ Rate limiting on auth endpoints
- ✅ Role-based access control (RBAC)

## Troubleshooting

### "Could not validate credentials"
1. Check cookie is set: `/debug/cookie-status`
2. Verify token is valid and not expired
3. Clear cookies and login again

### Database connection errors
1. Check `DATABASE_URL` in `.env`
2. Verify PostgreSQL is running: `docker-compose ps postgres`
3. Test connection: `psql $DATABASE_URL`

### Redis connection errors
1. Check `REDIS_URL` in `.env`
2. Verify Redis is running: `docker-compose ps redis`
3. App continues without Redis (degraded mode)

### PDF processing stuck
1. Check WebSocket connection: Browser DevTools → Network
2. Verify `LLAMAPARSE_API_KEY` is set
3. Check logs for API errors

### Simulation not responding
1. Verify `OPENAI_API_KEY` is valid
2. Check API rate limits
3. Look for errors in backend logs

## Useful Links

- **API Docs**: http://localhost:8000/docs (when running locally)
- **Frontend**: http://localhost:3000
- **Database Admin**: See `backend/db_admin/`
- **Full Architecture**: See `docs/architecture/`

## Quick Module Lookup

| Feature | Module | Key Files |
|---------|--------|-----------|
| PDF Upload | `pdf_processing` | pipeline.py, parser_service.py |
| Simulations | `simulation` | router.py, service.py |
| Login/OAuth | `auth` | service.py, provider.py |
| Cohorts | `professor` | routers/cohorts.py |
| Progress | `student` | routers/simulation_instances.py |
| AI Personas | `agents` | persona_agent.py |
| Database | `common/db` | core.py, models/ |
| Config | `common` | config.py |

## Module Communication

```mermaid
graph LR
    A[simulation] -->|Uses| B[agents/persona]
    C[pdf_processing] -->|Creates| D[scenarios]
    E[professor] -->|Manages| F[cohorts]
    G[student] -->|Joins| F
    G -->|Starts| A
    E -->|Creates| D
    
    A -->|Saves to| H[(Database)]
    C -->|Saves to| H
    E -->|Saves to| H
    G -->|Saves to| H
```

## Next Steps

- Read [System Overview](./architecture/system-overview.md) for detailed architecture
- See [Architecture Diagram](./architecture/architecture-diagram.md) for visual representations
- Check [Modular Migration Guide](./architecture/modular-migration-guide.md) for development patterns
- Review [Developer Guide](./Developer_Guide.md) for detailed setup instructions

