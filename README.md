# n-aible EdTech Simulation Platform

This directory contains a full-stack application with a modular backend architecture and a Next.js frontend. The backend follows the architecture described in `architecture.md`, providing a clean, modular baseline that contributors can implement domain-by-domain.

## Current Scope

### Backend
- **Auth module** (`modules/auth`) - Fully implemented with working endpoints and comprehensive tests
- **Other modules** (simulation, PDF processing, professor, student, notifications, publishing) exist as placeholder packages with scaffolded structure
- **Shared infrastructure** under `backend/common/` (config, db core, utilities, services) provides reusable components

### Frontend
- **Authentication** - Login and registration pages with role selection
- **API Integration** - Next.js API routes that proxy to backend endpoints
- **Auth Context** - React context for managing authentication state
- **UI Components** - Basic shadcn/ui components for forms and buttons

## Prerequisites

### Backend
- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager (install with `pip install uv` or `brew install uv`)

### Frontend
- Node.js 18.x or higher (install from [nodejs.org](https://nodejs.org/))
- npm (comes with Node.js) or pnpm (install with `npm install -g pnpm`)

## Getting Started

### 1. Backend Setup

#### Install Dependencies

Navigate to the backend directory and sync dependencies using `uv`:

```bash
cd backend
uv sync
```

This will:
- Create a virtual environment (`.venv`)
- Install all dependencies from `pyproject.toml`
- Install test dependencies (pytest, pytest-asyncio)

<Note>
`uv sync` is equivalent to `pip install` but much faster. It automatically manages the virtual environment and installs all required packages.
</Note>

#### Run Database Migrations

Before starting the backend, apply database migrations:

```bash
cd backend
uv run alembic upgrade head
```

This creates the database schema. See [Database Migrations](#database-migrations) for more details.

#### Start the Backend Server

Start the FastAPI development server:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Or if you've activated the virtual environment:

```bash
cd backend
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000` with:
- Interactive API docs at `http://localhost:8000/docs`
- Health check at `http://localhost:8000/health`
- Auth endpoints at `http://localhost:8000/api/auth/*`

#### Database

- Defaults to SQLite via `common/config.py` (see `database_url`)
- Database file: `app.db` (created automatically in `backend/` directory)
- **Migrations**: Managed with Alembic (see [Database Migrations](#database-migrations) section)
- Tables are created via migrations, not automatically on startup

### 2. Frontend Setup

#### Install Dependencies

Navigate to the frontend directory and install dependencies:

```bash
cd frontend
npm install
```

Or if you prefer using `pnpm`:

```bash
cd frontend
pnpm install
```

#### Configure Environment Variables

Create a `.env.local` file in the `frontend/` directory:

```bash
cd frontend
cat > .env.local << EOF
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF
```

This tells the frontend where to find the backend API.

#### Start the Frontend Development Server

Start the Next.js development server:

```bash
cd frontend
npm run dev
```

Or with `pnpm`:

```bash
cd frontend
pnpm dev
```

The frontend will be available at `http://localhost:3000` with:
- Login page at `http://localhost:3000/login`
- Signup page at `http://localhost:3000/signup`
- Home page redirects to login

### 3. Running Both Services

To run both backend and frontend simultaneously, open two terminal windows:

**Terminal 1 - Backend:**
```bash
cd backend
uv run uvicorn app.main:app --reload
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

Then visit `http://localhost:3000` in your browser to access the application.

<Info>
Make sure the backend is running before starting the frontend, as the frontend needs to connect to the API for authentication and other features.
</Info>

## Database Migrations

This project uses [Alembic](https://alembic.sqlalchemy.org/) for database schema versioning and migrations.

### Migration Structure

```
backend/
├── alembic.ini              # Alembic configuration
└── migrations/
    ├── env.py              # Migration environment (imports all models)
    ├── versions/           # Migration files
    └── README.md          # Detailed migration guide
```

### Creating Migrations

When you modify SQLAlchemy models, create a migration:

```bash
# From the backend directory
cd backend

# Create migration with autogenerate (recommended)
uv run alembic revision --autogenerate -m "description of changes"

# Or create empty migration
uv run alembic revision -m "description of changes"
```

**Important**: Always review auto-generated migrations before applying them!

### Applying Migrations

```bash
# Apply all pending migrations
uv run alembic upgrade head

# Apply one migration
uv run alembic upgrade +1

# Apply to specific revision
uv run alembic upgrade <revision_id>
```

### Rolling Back Migrations

```bash
# Rollback one migration
uv run alembic downgrade -1

# Rollback to specific revision
uv run alembic downgrade <revision_id>

# Rollback all migrations
uv run alembic downgrade base
```

### Checking Migration Status

```bash
# Show current database version
uv run alembic current

# Show migration history
uv run alembic history

# Show pending migrations
uv run alembic heads
```

### Adding Models from New Modules

When you add models to a new module:

1. **Create the model** in `modules/<module_name>/models.py`
2. **Import it in `migrations/env.py`**:
   ```python
   from modules.<module_name> import models as <module_name>_models  # noqa: F401
   ```
3. **Create migration**:
   ```bash
   uv run alembic revision --autogenerate -m "add <module_name> models"
   ```

### Migration Best Practices

- ✅ **Always review** auto-generated migrations before applying
- ✅ **Test migrations** on development database first
- ✅ **Use descriptive messages** (e.g., "add_user_profile_fields")
- ✅ **Never edit existing migrations** - create new ones instead
- ✅ **Keep migrations small** - one logical change per migration
- ✅ **Test rollback** to ensure migrations are reversible

### Example Workflow

```bash
# 1. Make changes to models
# Edit modules/auth/models.py

# 2. Create migration
uv run alembic revision --autogenerate -m "add user profile fields"

# 3. Review the generated migration file
# Check migrations/versions/YYYYMMDD_HHMM-xxxxx_add_user_profile_fields.py

# 4. Apply migration
uv run alembic upgrade head

# 5. Verify changes
# Check database schema matches your models
```

For more details, see `migrations/README.md`.

## Development Workflow

Follow this workflow when implementing new API endpoints:

### Step 1: Choose a Module

Pick a module from `backend/modules/` to implement:
- `auth/` - Authentication (✅ Complete)
- `simulation/` - Simulation execution
- `pdf_processing/` - PDF to scenario pipeline
- `professor/` - Professor features
- `student/` - Student features
- `notifications/` - Notification system
- `publishing/` - Marketplace features

### Step 2: Implement the Module

Each module follows a consistent structure:

```
modules/<feature>/
├── router.py          # FastAPI endpoints (HTTP layer)
├── service.py         # Business logic
├── repository.py      # Data access (database queries)
├── schemas/           # Pydantic models
│   ├── dto.py         # Request/response DTOs
│   └── models.py       # Domain models
└── models.py          # SQLAlchemy ORM models (if needed)
```

**Implementation order:**
1. Define schemas in `schemas/dto.py` (request/response models)
2. Create ORM models in `models.py` (if needed)
3. **Create database migration** (see [Database Migrations](#database-migrations))
4. Implement repository in `repository.py` (database queries)
5. Implement service in `service.py` (business logic)
6. Create router in `router.py` (HTTP endpoints)
7. Register router in `app/api/__init__.py`

**Example (Auth module reference):**
- See `modules/auth/` for a complete implementation example
- All files are fully implemented and tested

### Step 3: Write Tests

Tests are located in `backend/tests/modules/<feature>/test_router.py`

**Test structure:**
```python
def test_endpoint_success(client):
    """Test successful request."""
    response = client.post("/api/feature/endpoint", json=payload)
    assert response.status_code == status.HTTP_200_OK
    # ... more assertions
```

**Run tests:**
```bash
# Run all tests
uv run pytest tests/ -v

# Run tests for a specific module
uv run pytest tests/modules/auth/ -v

# Run a specific test file
uv run pytest tests/modules/auth/test_router.py -v

# Run with coverage
uv run pytest tests/ --cov=modules --cov-report=html
```

**Test fixtures:**
- `client` - FastAPI TestClient with database override
- `db_session` - Fresh database session for each test
- See `tests/conftest.py` for fixture definitions

<Info>
Each test gets a clean database state, ensuring tests don't interfere with each other.
</Info>

### Step 4: Verify Your Implementation

1. **Start the server:**
   ```bash
   uv run uvicorn app.main:app --reload
   ```

2. **Test manually:**
   - Visit `http://localhost:8000/docs` for interactive API docs
   - Test endpoints using the Swagger UI

3. **Run automated tests:**
   ```bash
   uv run pytest tests/modules/<your-module>/ -v
   ```

4. **Check test coverage:**
   ```bash
   uv run pytest tests/ --cov=modules/<your-module> --cov-report=term-missing
   ```

### Step 5: Update Documentation

After implementing and testing your endpoints, document them in Mintlify:

1. **Navigate to mintlify-docs:**
   ```bash
   cd mintlify-docs
   ```

2. **Create API documentation:**
   - Create endpoint docs in `api/<module>/<endpoint>.mdx`
   - Follow the format of existing docs (see `api/auth/register.mdx` as reference)
   - Include request/response examples, parameters, and error cases

3. **Update development docs if needed:**
   - Add examples to `development/getting-started.mdx` if workflow changes
   - Update `development/testing.mdx` with new test patterns

4. **Commit and push to mintlify repository:**
   ```bash
   git add .
   git commit -m "Add documentation for <module> endpoints"
   git push origin main
   ```

<Info>
The `mintlify-docs/` directory is a separate git repository. Changes here are pushed to the Mintlify documentation site, which auto-deploys when pushed to the main branch.
</Info>

<Tip>
Document your endpoints as you implement them - it's easier to document while the code is fresh in your mind!
</Tip>

## Testing Guide

### Test Location

Tests mirror the module structure:
```
tests/
├── conftest.py              # Shared fixtures (client, db_session)
├── modules/
│   └── auth/
│       └── test_router.py  # Auth endpoint tests
└── common/
    └── fixtures.py         # Common test utilities
```

### Writing Tests

Follow the auth module test pattern (`tests/modules/auth/test_router.py`):

1. **Test success cases** - Happy path scenarios
2. **Test validation** - Input validation errors
3. **Test error cases** - Business logic errors
4. **Test edge cases** - Boundary conditions

**Example test:**
```python
def test_register_user_success(client):
    """Test successful user registration."""
    payload = {
        "email": "test@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    }
    response = client.post("/api/auth/register", json=payload)
    
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == payload["email"]
    assert "id" in data
```

### Test Best Practices

- Each test should be independent
- Use descriptive test names (e.g., `test_register_user_duplicate_email`)
- Test both success and failure paths
- Assert on status codes AND response data
- Use fixtures for common setup

## Project Structure

```
n-aible_edtech_sims/
├── backend/              # FastAPI backend application
│   ├── alembic.ini      # Alembic migration configuration
│   ├── app/             # FastAPI application
│   │   ├── main.py      # Application entrypoint
│   │   ├── api/         # API router registration
│   │   └── dependencies.py  # Dependency injection
│   ├── common/          # Shared infrastructure
│   │   ├── config.py    # Settings (Pydantic)
│   │   ├── db/          # Database (SQLAlchemy)
│   │   ├── security/    # Auth utilities
│   │   └── services/    # Shared services
│   ├── migrations/      # Database migrations
│   │   ├── env.py       # Migration environment
│   │   └── versions/    # Migration files
│   ├── modules/         # Feature modules
│   │   ├── auth/        # ✅ Complete example
│   │   ├── simulation/  # Placeholder
│   │   └── ...
│   ├── tests/           # Test suite
│   │   ├── conftest.py  # Test fixtures
│   │   └── modules/     # Module tests
│   └── pyproject.toml    # Dependencies & config
│
└── frontend/             # Next.js frontend application
    ├── app/             # Next.js app directory
    │   ├── api/         # Next.js API routes (proxies to backend)
    │   ├── login/       # Login page
    │   ├── signup/      # Signup page
    │   └── layout.tsx   # Root layout
    ├── components/      # React components
    │   └── ui/          # UI component library (shadcn/ui)
    ├── lib/             # Utility libraries
    │   ├── api.ts       # API client
    │   ├── auth-context.tsx  # Auth context provider
    │   └── types.ts     # TypeScript types
    ├── package.json     # Node.js dependencies
    └── tsconfig.json    # TypeScript configuration
```

## Conventions to Follow

- **Routers are thin** - Validate requests, call services, return responses
- **Services contain logic** - Business rules, orchestration, validation
- **Repositories access data** - Database queries only, no business logic
- **No circular dependencies** - Modules import from `common/`, not each other
- **Use type hints** - Enable static type checking
- **Write tests** - Every endpoint should have tests

## Available Commands

### Backend Commands

```bash
# Navigate to backend directory
cd backend

# Install/update dependencies
uv sync

# Run development server
uv run uvicorn app.main:app --reload

# Database migrations
uv run alembic revision --autogenerate -m "description"  # Create migration
uv run alembic upgrade head                              # Apply migrations
uv run alembic downgrade -1                             # Rollback migration
uv run alembic current                                  # Check current version
uv run alembic history                                  # Show migration history

# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/modules/auth/test_router.py -v

# Run with coverage
uv run pytest tests/ --cov=modules --cov-report=html

# Check code formatting (if configured)
uv run black .
uv run isort .
```

### Frontend Commands

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install
# or
pnpm install

# Run development server
npm run dev
# or
pnpm dev

# Build for production
npm run build
# or
pnpm build

# Start production server
npm start
# or
pnpm start

# Run linter
npm run lint
# or
pnpm lint
```

## Quick Start Checklist

1. **Backend Setup:**
   - [ ] Install backend dependencies: `cd backend && uv sync`
   - [ ] Run migrations: `cd backend && uv run alembic upgrade head`
   - [ ] Start backend server: `cd backend && uv run uvicorn app.main:app --reload`
   - [ ] Verify backend is running at `http://localhost:8000/docs`

2. **Frontend Setup:**
   - [ ] Install frontend dependencies: `cd frontend && npm install`
   - [ ] Create `.env.local` with `NEXT_PUBLIC_API_URL=http://localhost:8000`
   - [ ] Start frontend server: `cd frontend && npm run dev`
   - [ ] Verify frontend is running at `http://localhost:3000`

3. **Test the Application:**
   - [ ] Visit `http://localhost:3000/login`
   - [ ] Try registering a new user at `http://localhost:3000/signup`
   - [ ] Test login with registered credentials

## Next Steps

1. **Pick a module** from `modules/` to implement
2. **Follow the auth module** (`modules/auth/`) as a reference
3. **Write tests** as you implement each endpoint
4. **Verify** using the interactive API docs at `/docs`
5. **Update frontend** to integrate new backend endpoints as you implement them

## Mintlify Documentation Workflow

The `mintlify-docs/` directory contains our public documentation site. It's a separate git repository that auto-deploys to Mintlify when pushed.

### When to Update Documentation

Update Mintlify docs when you:
- ✅ Add new API endpoints
- ✅ Change existing endpoint behavior
- ✅ Add new development workflows
- ✅ Update testing patterns
- ✅ Add new features or modules

### Documentation Structure

```
mintlify-docs/
├── api/                    # API endpoint documentation
│   └── auth/              # Module-specific endpoints
│       ├── register.mdx
│       └── login.mdx
├── development/           # Development guides
│   ├── getting-started.mdx
│   └── testing.mdx
└── docs.json              # Navigation configuration
```

### Updating API Documentation

1. **Create endpoint documentation:**
   ```bash
   cd mintlify-docs
   # Create new file: api/<module>/<endpoint>.mdx
   ```

2. **Follow the format:**
   - Use Mintlify components (`Endpoint`, `ParamField`, `ResponseField`, etc.)
   - Include request/response examples
   - Document all parameters and error cases
   - See `api/auth/register.mdx` as a reference

3. **Update navigation:**
   - Add new pages to `docs.json` under the appropriate section
   - Follow the existing navigation structure

4. **Preview locally:**
   ```bash
   cd mintlify-docs
   mint dev
   ```
   Visit `http://localhost:3000` to preview changes

5. **Commit and push:**
   ```bash
   git add .
   git commit -m "Add documentation for <module>/<endpoint>"
   git push origin main
   ```

<Info>
Mintlify automatically deploys changes when you push to the main branch. The documentation site will update within a few minutes.
</Info>

### Documentation Best Practices

- **Document as you code** - Easier to document while implementation is fresh
- **Include examples** - Show request/response examples in multiple languages
- **Document errors** - Include all possible error responses
- **Keep it updated** - Update docs when you change endpoints
- **Use Mintlify components** - Leverage built-in components for consistency

## Resources

- **Architecture**: See `architecture.md` for detailed architecture documentation
- **API Docs**: Interactive docs at `http://localhost:8000/docs` when server is running
- **Mintlify Docs**: See `mintlify-docs/` for comprehensive documentation
- **Mintlify Preview**: Run `mint dev` in `mintlify-docs/` to preview locally

---

This README provides everything you need to start developing. The auth module serves as a complete reference implementation with tests.
