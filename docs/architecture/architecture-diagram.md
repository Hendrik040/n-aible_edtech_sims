# AI Agent Education Platform - Architecture Diagram

## System Overview

This document provides a comprehensive visual representation of the AI Agent Education Platform architecture, showing the complete system from user interface to data storage, including the PDF-to-simulation pipeline and modular backend structure.

## High-Level System Architecture

```mermaid
graph TB
    subgraph "User Interface Layer"
        WEB[Web Browser<br/>Next.js 15 Frontend]
        MOBILE[Mobile Interface<br/>Responsive Design]
    end
    
    subgraph "Frontend Application (Next.js 15)"
        DASHBOARD[Dashboard<br/>/dashboard]
        CHATBOX[Chat Interface<br/>/student/simulation-instances]
        SIMULATION_BUILDER[Simulation Builder<br/>/professor/simulation-builder]
        COHORTS[Cohorts<br/>/professor/cohorts]
        PROFILE[Profile<br/>/profile]
    end
    
    subgraph "API Gateway & Middleware"
        FASTAPI[FastAPI Server<br/>app/main.py]
        AUTH[Authentication<br/>JWT + OAuth Middleware]
        CORS[CORS Middleware<br/>Cross-Origin Support]
        CACHE[Cache Layer<br/>Redis]
    end
    
    subgraph "Backend Modules (Feature-Based)"
        direction TB
        subgraph "modules/simulation"
            SIM_ROUTER[router.py<br/>Endpoints]
            SIM_SERVICE[service.py<br/>Business Logic]
            SIM_REPO[repository.py<br/>Data Access]
        end
        subgraph "modules/pdf_processing"
            PDF_ROUTER[router.py<br/>Endpoints]
            PDF_PIPELINE[pipeline.py<br/>Orchestration]
            PDF_SERVICES[parser_service.py<br/>ai_extraction_service.py]
        end
        subgraph "modules/auth"
            AUTH_ROUTER[router.py<br/>Endpoints]
            AUTH_SERVICE[service.py<br/>Auth Logic]
            AUTH_PROVIDER[provider.py<br/>OAuth]
        end
        subgraph "modules/professor"
            PROF_ROUTER[router.py<br/>Main Router]
            PROF_SUBROUTERS[routers/<br/>cohorts, grading, invitations]
        end
        subgraph "modules/student"
            STU_ROUTER[router.py<br/>Main Router]
            STU_SUBROUTERS[routers/<br/>simulation_instances, cohorts]
        end
    end
    
    subgraph "Common Infrastructure (common/)"
        direction TB
        CONFIG[config.py<br/>Settings]
        DB_CORE[db/core.py<br/>Engine & Sessions]
        DB_MODELS[db/models/<br/>user, cache, notifications]
        UTILS[utils/<br/>auth, redis, id_generator]
    end
    
    subgraph "AI Agents"
        PERSONA_AGENT[Persona Agent<br/>persona_agent.py]
        SUMMARIZATION_AGENT[Summarization Agent<br/>summarization_agent.py]
        GRADING_AGENT[Grading Agent<br/>grading_agent.py]
    end
    
    subgraph "External AI Services"
        OPENAI[OpenAI GPT-4<br/>Language Model]
        LLAMAPARSE[LlamaParse API<br/>PDF Processing]
        DALL_E[DALL-E 3<br/>Image Generation]
    end
    
    subgraph "Data Storage Layer"
        POSTGRES[(PostgreSQL Database<br/>Primary Data Store)]
        REDIS_STORE[(Redis<br/>Cache & Sessions)]
        FILE_STORAGE[File Storage<br/>PDFs & Images]
    end
    
    WEB --> DASHBOARD
    WEB --> CHATBOX
    WEB --> SIMULATION_BUILDER
    MOBILE --> DASHBOARD
    
    DASHBOARD --> FASTAPI
    CHATBOX --> FASTAPI
    SIMULATION_BUILDER --> FASTAPI
    COHORTS --> FASTAPI
    PROFILE --> FASTAPI
    
    FASTAPI --> AUTH
    FASTAPI --> CORS
    FASTAPI --> CACHE
    
    FASTAPI --> SIM_ROUTER
    FASTAPI --> PDF_ROUTER
    FASTAPI --> AUTH_ROUTER
    FASTAPI --> PROF_ROUTER
    FASTAPI --> STU_ROUTER
    
    SIM_ROUTER --> SIM_SERVICE
    SIM_SERVICE --> SIM_REPO
    SIM_SERVICE --> PERSONA_AGENT
    
    PDF_ROUTER --> PDF_PIPELINE
    PDF_PIPELINE --> PDF_SERVICES
    PDF_SERVICES --> LLAMAPARSE
    PDF_SERVICES --> OPENAI
    PDF_SERVICES --> DALL_E
    
    AUTH_ROUTER --> AUTH_SERVICE
    AUTH_SERVICE --> AUTH_PROVIDER
    
    PROF_ROUTER --> PROF_SUBROUTERS
    STU_ROUTER --> STU_SUBROUTERS
    
    SIM_REPO --> DB_CORE
    PDF_SERVICES --> DB_CORE
    AUTH_SERVICE --> DB_CORE
    
    DB_CORE --> DB_MODELS
    DB_CORE --> POSTGRES
    
    CACHE --> REDIS_STORE
    UTILS --> REDIS_STORE
    
    PERSONA_AGENT --> OPENAI
    SUMMARIZATION_AGENT --> OPENAI
    GRADING_AGENT --> OPENAI
    
    PDF_SERVICES --> FILE_STORAGE
```

## Backend Modular Architecture

The backend follows a **lightweight, feature-first layout** emphasizing pragmatic organization:

```mermaid
flowchart TB
    subgraph backend
        direction TB
        subgraph "app/ (FastAPI Wiring)"
            main[main.py<br/>Entry Point]
            deps[dependencies.py<br/>DI Providers]
            middleware[middleware.py<br/>CORS/Auth]
            lifespan[lifespan.py<br/>Startup/Shutdown]
        end

        subgraph "common/ (Shared Infrastructure)"
            config[config.py<br/>Pydantic Settings]
            logging[logging.py<br/>Structured Logs]
            exceptions[exceptions.py<br/>Custom Errors]
            
            subgraph "db/"
                core[core.py<br/>Engine/Sessions]
                base[base.py<br/>DeclarativeBase]
                models[models/<br/>user, cache, notifications]
                mixins[mixins.py<br/>Reusable Columns]
            end
            
            subgraph "utils/"
                auth_utils[auth.py<br/>JWT/Passwords]
                redis[redis_manager.py<br/>Redis Client]
                id_gen[id_generator.py<br/>ID Utils]
            end
        end

        subgraph "modules/ (Feature Domains)"
            direction TB
            
            subgraph "simulation/"
                sim_router[router.py]
                sim_service[service.py]
                sim_repo[repository.py]
                sim_schemas[schemas/]
            end
            
            subgraph "pdf_processing/"
                pdf_router[router.py]
                pdf_pipeline[pipeline.py]
                pdf_parser[parser_service.py]
                pdf_ai[ai_extraction_service.py]
                pdf_repo[repository.py]
            end
            
            subgraph "auth/"
                auth_router[router.py]
                auth_service[service.py]
                auth_provider[provider.py]
                auth_schemas[schemas.py]
            end
            
            subgraph "professor/"
                prof_router[router.py]
                prof_subrouters[routers/]
                prof_schemas[schemas/]
            end
            
            subgraph "student/"
                stu_router[router.py]
                stu_subrouters[routers/]
                stu_schemas[schemas/]
            end
        end

        subgraph "agents/ (AI Agents)"
            persona[persona_agent.py]
            grading[grading_agent.py]
            summarization[summarization_agent.py]
        end
    end

    main --> deps
    deps --> modules/
    modules/ --> common/
    sim_service --> agents/
    pdf_pipeline --> agents/
```

**Key Principles:**
- **One-way dependencies**: `app` → `modules` → `common` (prevents circular imports)
- **Feature ownership**: Each module owns router, service, repository, schemas
- **Shared models**: Common tables (User, Cache, Notifications) in `common/db/models/`
- **Domain models**: Feature-specific models in module directories
- **Repository pattern**: Data access abstraction for testability

## PDF-to-Simulation Pipeline Flow

```mermaid
sequenceDiagram
    participant U as User/Professor
    participant F as Frontend
    participant API as FastAPI Gateway
    participant PDFRouter as modules/pdf_processing/router
    participant Pipeline as pipeline.py
    participant Parser as parser_service.py
    participant AI as ai_extraction_service.py
    participant LP as LlamaParse API
    participant GPT as OpenAI GPT-4
    participant DALL as DALL-E 3
    participant DB as PostgreSQL

    U->>F: Upload PDF case study
    F->>API: POST /api/parse-pdf/upload
    API->>PDFRouter: Route request
    PDFRouter->>Pipeline: process_pdf(file)
    
    Note over Pipeline: Step 1: Parse PDF
    Pipeline->>Parser: extract_text_from_pdf()
    Parser->>LP: Parse PDF with LlamaParse
    LP-->>Parser: Structured text content
    Parser-->>Pipeline: Cleaned text
    
    Note over Pipeline: Step 2: Extract Metadata
    Pipeline->>AI: extract_personas_and_metadata()
    AI->>GPT: Analyze business case
    GPT-->>AI: Title, description, personas, roles
    AI-->>Pipeline: Scenario metadata
    
    Note over Pipeline: Step 3: Generate Scenes
    Pipeline->>AI: generate_timeline_scenes()
    AI->>GPT: Create scene sequence
    GPT-->>AI: Scene timeline with goals
    AI-->>Pipeline: Scene data
    
    Note over Pipeline: Step 4: Generate Images
    Pipeline->>AI: generate_scene_images()
    AI->>DALL: Create professional images
    DALL-->>AI: Scene image URLs
    AI-->>Pipeline: Image URLs
    
    Note over Pipeline: Step 5: Save to Database
    Pipeline->>DB: Save scenario, personas, scenes
    DB-->>Pipeline: Scenario ID
    
    Pipeline-->>PDFRouter: Processing complete
    PDFRouter-->>API: Success response
    API-->>F: Scenario ready (ID: 123)
    F-->>U: Show generated scenario preview
```

## Simulation Execution Flow

```mermaid
sequenceDiagram
    participant S as Student
    participant F as Frontend
    participant API as FastAPI Gateway
    participant SimRouter as modules/simulation/router
    participant SimService as service.py
    participant SimRepo as repository.py
    participant Persona as PersonaAgent
    participant GPT as OpenAI GPT-4
    participant DB as PostgreSQL
    participant Cache as Redis Cache

    S->>F: Start simulation (scenario_id: 123)
    F->>API: POST /api/simulation/start
    API->>SimRouter: Route request
    SimRouter->>SimService: start_simulation(scenario_id, user_id)
    
    SimService->>Cache: Check cached scenario?
    Cache-->>SimService: Cache miss
    SimService->>SimRepo: load_scenario_data()
    SimRepo->>DB: Query scenario, personas, scenes
    DB-->>SimRepo: Full scenario data
    SimRepo-->>SimService: Scenario object
    SimService->>Cache: Cache scenario data
    
    SimService->>SimRepo: create_user_progress()
    SimRepo->>DB: INSERT INTO user_progress
    DB-->>SimRepo: Progress record created
    SimRepo-->>SimService: UserProgress object
    
    SimService-->>SimRouter: Simulation initialized
    SimRouter-->>API: Success response
    API-->>F: Simulation ready (progress_id: 456)
    F-->>S: Display first scene
    
    Note over S,DB: User Interaction Loop
    S->>F: Send message to persona
    F->>API: POST /api/simulation/linear-chat
    API->>SimRouter: Route chat message
    SimRouter->>SimService: process_chat_message()
    
    SimService->>SimRepo: get_conversation_history()
    SimRepo->>DB: Query conversation_logs
    DB-->>SimRepo: Recent messages
    SimRepo-->>SimService: Conversation context
    
    SimService->>Persona: generate_response(message, context)
    Persona->>GPT: Generate persona response
    GPT-->>Persona: AI-generated response
    Persona-->>SimService: Persona message
    
    SimService->>SimRepo: save_conversation()
    SimRepo->>DB: INSERT INTO conversation_logs
    
    SimService->>SimService: check_scene_completion()
    alt Scene Complete
        SimService->>SimRepo: mark_scene_complete()
        SimRepo->>DB: UPDATE user_progress
        SimService->>SimRepo: load_next_scene()
        SimRepo->>DB: Query next scene
        DB-->>SimRepo: Next scene data
        SimRepo-->>SimService: Next scene
        Note over SimService: Prepare scene transition
    end
    
    SimService-->>SimRouter: Response with persona message
    SimRouter-->>API: Chat response
    API-->>F: Display response
    F-->>S: Show persona message
```

## Authentication & Authorization Flow

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant API as FastAPI
    participant AuthRouter as modules/auth/router
    participant AuthService as auth/service
    participant AuthProvider as auth/provider (OAuth)
    participant Google as Google OAuth
    participant DB as PostgreSQL
    
    alt Google OAuth Login
        U->>F: Click "Login with Google"
        F->>API: GET /api/auth/google
        API->>AuthRouter: Route OAuth request
        AuthRouter->>AuthProvider: initiate_oauth()
        AuthProvider->>Google: OAuth authorization request
        Google-->>U: Google login page
        U->>Google: Provide credentials
        Google->>API: OAuth callback with code
        API->>AuthRouter: Handle callback
        AuthRouter->>AuthProvider: exchange_code_for_token()
        AuthProvider->>Google: Exchange code for token
        Google-->>AuthProvider: Access token + user info
        AuthProvider->>DB: Find or create user
        DB-->>AuthProvider: User record
        AuthProvider->>AuthService: create_jwt_token()
        AuthService-->>AuthProvider: JWT token
        AuthProvider-->>AuthRouter: User + token
        AuthRouter-->>API: Set HttpOnly cookie
        API-->>F: Redirect to dashboard
        F-->>U: Dashboard view
    else Email/Password Login
        U->>F: Enter email & password
        F->>API: POST /users/login
        API->>AuthRouter: Route login request
        AuthRouter->>AuthService: authenticate_user()
        AuthService->>DB: Query user by email
        DB-->>AuthService: User record
        AuthService->>AuthService: verify_password()
        alt Password Valid
            AuthService->>AuthService: create_jwt_token()
            AuthService-->>AuthRouter: JWT token
            AuthRouter-->>API: Set HttpOnly cookie
            API-->>F: Success + user data
            F-->>U: Dashboard view
        else Password Invalid
            AuthService-->>AuthRouter: Authentication failed
            AuthRouter-->>API: 401 Unauthorized
            API-->>F: Error response
            F-->>U: "Invalid credentials"
        end
    end
```

## Database Schema Architecture

```mermaid
erDiagram
    users {
        integer id PK
        string user_id UK "Role-based ID (ST-xxxxx/PR-xxxxx)"
        string email UK
        string full_name
        string username UK
        string password_hash "Nullable for OAuth users"
        text bio
        string avatar_url
        string role "student/professor/admin"
        string google_id UK "For OAuth"
        string provider "password/google"
        integer published_scenarios
        integer total_simulations
        float reputation_score
        boolean profile_public
        boolean allow_contact
        boolean is_active
        boolean is_verified
        timestamp last_activity
        timestamp created_at
        timestamp updated_at
    }

    scenarios {
        integer id PK
        string unique_id UK
        string title
        text description
        text challenge
        string industry
        jsonb learning_objectives
        string source_type "pdf/manual/template"
        text pdf_content
        string student_role
        string category
        string difficulty_level
        integer estimated_duration
        jsonb tags
        string status "draft/active/archived"
        boolean is_draft
        boolean is_public
        boolean is_template
        integer created_by FK
        integer published_version_id FK
        jsonb grading_config
        text grading_prompt
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at "Soft delete"
    }

    scenario_personas {
        integer id PK
        integer scenario_id FK
        string name
        string role
        text background
        text correlation
        jsonb primary_goals
        jsonb personality_traits "Structured personality data"
        text system_prompt "AI prompt template"
        string image_url
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }

    scenario_scenes {
        integer id PK
        integer scenario_id FK
        string title
        text description
        text user_goal
        integer scene_order
        integer estimated_duration
        integer max_attempts
        integer timeout_turns
        float success_threshold
        jsonb goal_criteria
        jsonb hint_triggers
        text scene_context
        jsonb persona_instructions
        string success_metric
        string image_url
        string image_prompt
        timestamp created_at
        timestamp updated_at
    }

    user_progress {
        integer id PK
        integer user_id FK
        integer scenario_id FK
        integer current_scene_id FK
        string simulation_status "not_started/in_progress/completed/abandoned"
        jsonb scenes_completed
        integer total_attempts
        integer hints_used
        integer forced_progressions
        jsonb orchestrator_data "ChatOrchestrator state"
        float completion_percentage
        integer total_time_spent
        integer session_count
        float final_score
        timestamp started_at
        timestamp completed_at
        timestamp last_activity
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at "Soft delete"
    }

    conversation_logs {
        integer id PK
        integer user_progress_id FK
        integer scene_id FK
        string message_type "user/system/persona"
        string sender_name
        integer persona_id FK
        text message_content
        integer message_order
        integer attempt_number
        boolean is_hint
        jsonb ai_context_used "Context passed to AI"
        string ai_model_version
        float processing_time
        string user_reaction
        boolean led_to_progress
        timestamp timestamp
    }

    cohorts {
        integer id PK
        string name
        text description
        integer professor_id FK
        integer scenario_id FK
        timestamp start_date
        timestamp end_date
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    cohort_memberships {
        integer id PK
        integer cohort_id FK
        integer student_id FK
        string status "active/completed/dropped"
        float completion_percentage
        timestamp enrolled_at
        timestamp completed_at
    }

    cohort_invitations {
        integer id PK
        integer cohort_id FK
        integer professor_id FK
        integer student_id FK
        string email
        string status "pending/accepted/declined/expired"
        string invitation_token UK
        timestamp expires_at
        timestamp created_at
        timestamp accepted_at
    }

    notifications {
        integer id PK
        integer user_id FK
        string type "invitation/grading/progress"
        string title
        text message
        jsonb data "Additional context"
        boolean is_read
        timestamp created_at
        timestamp read_at
    }

    users ||--o{ scenarios : creates
    users ||--o{ user_progress : tracks
    users ||--o{ cohorts : teaches
    users ||--o{ cohort_memberships : enrolled_in
    users ||--o{ notifications : receives

    scenarios ||--o{ scenario_personas : contains
    scenarios ||--o{ scenario_scenes : contains
    scenarios ||--o{ user_progress : simulates
    scenarios ||--o{ cohorts : used_in

    scenario_personas ||--o{ conversation_logs : speaks_as
    scenario_scenes ||--o{ conversation_logs : contains
    scenario_scenes ||--o{ user_progress : current_scene

    user_progress ||--o{ conversation_logs : records

    cohorts ||--o{ cohort_memberships : contains
    cohorts ||--o{ cohort_invitations : invites_to
```

## Caching Architecture

```mermaid
graph TB
    subgraph "Cache Strategy"
        API[API Request] --> CHECK{Cache Hit?}
        CHECK -->|Yes| REDIS_HIT[Redis Cache]
        CHECK -->|No| DB[Database Query]
        DB --> STORE[Store in Redis]
        STORE --> RETURN[Return Data]
        REDIS_HIT --> RETURN
    end

    subgraph "Cache Types"
        AI_CACHE[AI Response Cache<br/>TTL: 1 hour]
        DB_CACHE[DB Query Cache<br/>TTL: 5 minutes]
        SESSION_CACHE[Session Cache<br/>TTL: 30 minutes]
        SCENARIO_CACHE[Scenario Data Cache<br/>TTL: 15 minutes]
    end

    subgraph "Cache Invalidation"
        UPDATE[Data Update] --> INVALIDATE{Invalidate Cache}
        INVALIDATE --> CLEAR_USER[Clear User Cache]
        INVALIDATE --> CLEAR_SCENARIO[Clear Scenario Cache]
        INVALIDATE --> CLEAR_AI[Clear AI Cache]
    end

    RETURN --> AI_CACHE
    RETURN --> DB_CACHE
    RETURN --> SESSION_CACHE
    RETURN --> SCENARIO_CACHE
```

## Performance Optimization Strategy

```mermaid
graph LR
    subgraph "Request Optimization"
        REQ[API Request] --> ASYNC[Async Processing]
        ASYNC --> CACHE_LAYER[Cache Layer]
        CACHE_LAYER --> RESULT[Fast Response]
    end

    subgraph "Database Optimization"
        QUERY[DB Query] --> INDEX[Indexed Queries]
        INDEX --> POOL[Connection Pool]
        POOL --> EAGER[Eager Loading]
        EAGER --> FAST_DB[Optimized Result]
    end

    subgraph "AI Optimization"
        AI_REQ[AI Request] --> BATCH[Request Batching]
        BATCH --> AI_CACHE[Response Cache]
        AI_CACHE --> PROMPT[Prompt Optimization]
        PROMPT --> EFFICIENT[Efficient AI Calls]
    end

    RESULT --> RESPONSE[Client Response]
    FAST_DB --> RESPONSE
    EFFICIENT --> RESPONSE
```

## Security Architecture

```mermaid
graph TB
    subgraph "Authentication Layer"
        JWT[JWT Tokens<br/>30min expiry]
        OAUTH[Google OAuth<br/>Secure flow]
        COOKIE[HttpOnly Cookies<br/>Secure + SameSite]
    end

    subgraph "Authorization Layer"
        RBAC[Role-Based Access<br/>student/professor/admin]
        OWNERSHIP[Resource Ownership<br/>creator checks]
        PERMISSION[Permission Checks<br/>require_admin()]
    end
    
    subgraph "Data Protection"
        HASH[Password Hashing<br/>bcrypt]
        VALIDATION[Input Validation<br/>Pydantic schemas]
        SANITIZATION[SQL Injection Prevention<br/>SQLAlchemy ORM]
        ENCRYPTION[Data Encryption<br/>PostgreSQL SSL]
    end

    subgraph "API Security"
        RATE_LIMIT[Rate Limiting<br/>Per user/endpoint]
        CORS_POLICY[CORS Policy<br/>Restricted origins]
        HTTPS[HTTPS Only<br/>Production]
    end

    JWT --> RBAC
    OAUTH --> RBAC
    COOKIE --> JWT
    RBAC --> OWNERSHIP
    OWNERSHIP --> PERMISSION
    HASH --> VALIDATION
    VALIDATION --> SANITIZATION
    RATE_LIMIT --> CORS_POLICY
    CORS_POLICY --> HTTPS
```

## Deployment Architecture

```mermaid
graph TB
    subgraph "Development"
        DEV_FE[Next.js Dev Server<br/>localhost:3000]
        DEV_BE[FastAPI Dev Server<br/>localhost:8000]
        DEV_DB[(PostgreSQL<br/>Docker/Local)]
        DEV_REDIS[(Redis<br/>Docker/Local)]
    end

    subgraph "Staging"
        STAGE_FE[Frontend<br/>Railway Staging]
        STAGE_BE[Backend<br/>Railway Staging]
        STAGE_DB[(PostgreSQL<br/>Railway)]
        STAGE_REDIS[(Redis<br/>Railway)]
    end

    subgraph "Production"
        PROD_FE[Frontend<br/>Railway Production]
        PROD_BE[Backend<br/>Railway Production<br/>Gunicorn + Uvicorn]
        PROD_DB[(PostgreSQL<br/>Railway<br/>Connection Pooling)]
        PROD_REDIS[(Redis<br/>Railway<br/>Persistent)]
        CDN[CDN<br/>Static Assets]
    end

    DEV_FE --> DEV_BE
    DEV_BE --> DEV_DB
    DEV_BE --> DEV_REDIS

    STAGE_FE --> STAGE_BE
    STAGE_BE --> STAGE_DB
    STAGE_BE --> STAGE_REDIS

    PROD_FE --> CDN
    PROD_FE --> PROD_BE
    PROD_BE --> PROD_DB
    PROD_BE --> PROD_REDIS
```

## Technology Stack

### Backend Technologies
- **FastAPI** - High-performance async web framework with automatic OpenAPI docs
- **Python 3.11+** - Modern Python with type hints and async support
- **SQLAlchemy** - Advanced ORM with PostgreSQL integration and JSONB support
- **Pydantic** - Data validation, serialization, and settings management
- **Alembic** - Database migration management with version control
- **Redis** - High-performance caching and session storage
- **uv** - Fast Python package installer and dependency manager

### AI/ML Technologies
- **OpenAI GPT-4** - Advanced language model for persona interactions and content generation
- **LlamaParse** - Intelligent PDF processing and structured data extraction
- **DALL-E 3** - AI image generation for scene visualization
- **LangChain** - AI framework for agent orchestration and memory management

### Frontend Technologies
- **Next.js 15** - React framework with TypeScript and App Router
- **Tailwind CSS** - Utility-first CSS framework
- **shadcn/ui** - Modern component library built on Radix UI
- **React Hook Form** - Performant form management with validation
- **Zod** - TypeScript-first schema validation

### Database & Storage
- **PostgreSQL** - Primary database with JSONB and vector extensions
- **Redis** - Caching and session management
- **Wasabi/AWS S3** - Object storage for files and images

### DevOps & Infrastructure
- **Railway** - Cloud deployment platform
- **Docker** - Containerization for local development
- **GitHub Actions** - CI/CD pipeline
- **Pytest** - Comprehensive testing framework

## Key Architecture Principles

### 1. Modular Design
- Feature-based organization for better code navigation
- Self-contained modules with clear boundaries
- Minimal cross-module dependencies

### 2. Separation of Concerns
- Routers handle HTTP concerns (validation, status codes)
- Services contain business logic (orchestration, transformations)
- Repositories abstract data access (queries, transactions)

### 3. Performance First
- Redis caching for frequently accessed data
- Async processing for I/O-bound operations
- Database query optimization with indexes and eager loading
- Connection pooling for database efficiency

### 4. Security by Design
- JWT-based authentication with HttpOnly cookies
- Role-based access control for authorization
- Input validation with Pydantic schemas
- SQL injection prevention via SQLAlchemy ORM

### 5. Scalability
- Stateless API design for horizontal scaling
- Feature modules can scale independently
- Caching strategy reduces database load
- Background task processing for long-running operations

This architecture provides a robust, scalable, and maintainable foundation for the AI Agent Education Platform, supporting both current educational requirements and future growth in the AI-powered learning space.
