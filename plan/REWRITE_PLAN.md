# Rewrite: `n-aible_edtech_sims` backend on the Claude Agent SDK

## Context

The current backend (`backend/`) is a FastAPI + SQLAlchemy + Alembic monolith whose AI layer is built on LangChain 0.3.x + OpenAI GPT-4o. Twelve files drive the AI behavior:

- `modules/simulation/core/orchestrator.py` — ChatOrchestrator (linear scene progression)
- `modules/simulation/agents/{persona_agent,grading_agent,summarization_agent,callbacks}.py` — LangChain `AgentExecutor` + `ConversationBufferWindowMemory`
- `common/services/simulation_helper/{langchain_service,scene_memory_service,memory_service,grading_vector_store,grading_embedding_service}.py` — PGVector wrapper, RAG retrieval, grading embeddings
- `modules/pdf_processing/{ai_extraction_service,image_generation_service}.py` — direct OpenAI calls (persona/scene extraction + DALL·E avatars)

We want a cleaner AI runtime that:
1. uses the **Claude Agent SDK** (Python) as the agent loop instead of LangChain,
2. picks up newer, stronger models (Claude 4.5/4.6 for chat, Gemini 2.5 "nano-banana" for images, OpenAI embeddings kept for pgvector compatibility),
3. exposes simulation capabilities (memory retrieval, grading, scene transitions, PDF extraction) as **in-process MCP tools** so Claude can orchestrate them,
4. models persona chat as **one resumable SDK session per (user_progress, persona) pair**,
5. ships side-by-side with the existing backend (new `backend_v2/` tree) so the two can run in parallel until parity is verified.

Outcome: a smaller, more maintainable AI layer with better conversation quality and pluggable model/provider choices.

---

## High-level architecture

```
backend_v2/
├── app/                     # FastAPI entrypoint (copied, trimmed)
├── common/
│   ├── db/                  # ← REUSE verbatim from backend/ (models + Alembic)
│   ├── config.py            # + ANTHROPIC_API_KEY, GOOGLE_GENAI_API_KEY, model names
│   └── services/
│       ├── cache_service.py        # reuse (Redis)
│       ├── s3_service.py           # reuse
│       ├── embeddings_service.py   # NEW — OpenAI text-embedding-3-small (thin client, no LangChain)
│       ├── pgvector_store.py       # NEW — direct psycopg + pgvector SQL (replaces PGVector wrapper)
│       └── image_service.py        # NEW — Gemini 2.5 Flash Image ("nano-banana") + OpenAI fallback
└── modules/
    ├── auth/                # copy from backend/ (done; no AI)
    ├── cohorts/             # copy from backend/
    ├── notifications/       # copy from backend/
    ├── professor/           # copy from backend/
    ├── student/             # copy from backend/
    ├── publishing/          # copy from backend/
    ├── pdf_processing/
    │   ├── router.py
    │   └── agent_extraction.py     # NEW — Agent SDK-driven extraction
    └── simulation/
        ├── router.py
        ├── handlers/chat_handler.py   # NEW — thin, streams SDK messages to client
        ├── orchestrator.py            # NEW — owns session lifecycle, no LLM calls
        ├── persona_runtime.py         # NEW — builds ClaudeAgentOptions per persona
        ├── prompts/
        │   ├── persona_system.py      # Big Five → system prompt (port from persona_agent.py)
        │   ├── grading_system.py
        │   └── summarization_system.py
        └── mcp/
            ├── server.py              # create_sdk_mcp_server assembly
            ├── memory_tools.py        # scene context + hybrid memory retrieval
            ├── grading_tools.py       # submit grading, look up rubric chunks
            ├── scene_tools.py         # advance_scene, complete_scene
            └── extraction_tools.py    # PDF persona/scene extraction
```

### Agent topology

- **Persona chat (per student turn):**
  `chat_handler` → loads/creates session id from `agent_sessions` row → calls `claude_agent_sdk.query(prompt=user_message, options=ClaudeAgentOptions(resume=session_id, system_prompt=persona_prompt, mcp_servers={"sim": sim_server}, allowed_tools=[mcp__sim__recall_memory, mcp__sim__lookup_rubric], tools=[]))` → streams `AssistantMessage` text blocks back over WebSocket/SSE.
  - `tools=[]` removes Claude Code's built-in Read/Edit/Bash from the persona's context — personas are actors, not coders.
  - Session ID stored in `agent_sessions.session_id` (existing column, repurposed).
- **Grading (at scene completion):** one-shot `query()` with `grading_system.py` prompt, `allowed_tools=["mcp__sim__lookup_rubric","mcp__sim__submit_grade"]`. Runs on Claude Haiku 4.5 for cost.
- **Summarization (at scene end):** one-shot `query()` with scene transcript in prompt; writes `conversation_summaries` via `mcp__sim__write_summary`. Haiku 4.5.
- **PDF extraction (uploaded case study):** orchestrator `query()` with `allowed_tools=["mcp__sim__extract_personas","mcp__sim__extract_scenes","mcp__sim__extract_objectives"]`. Tool handlers wrap structured JSON parsing.

### Model matrix (2026-04 targets)

| Job | Model | Why |
| --- | --- | --- |
| Persona chat | `claude-sonnet-4-6` (default) / `claude-opus-4-6` (premium cohorts) | Best long-context role-play; SDK-native |
| Grading + summarization | `claude-haiku-4-5-20251001` | Cheap, fast, structured-output friendly |
| Embeddings | OpenAI `text-embedding-3-small` | Keep to stay compatible with existing `vector_embeddings` rows; no migration needed |
| Avatar + scene images | Google Gemini 2.5 Flash Image (a.k.a. "nano-banana") | User's preferred provider; cheaper than DALL·E 3; OpenAI stays as fallback behind a feature flag |
| PDF structural parse (pre-LLM) | LlamaParse (keep) | Unchanged |

All model names live in `common/config.py` as env-overridable strings so we can A/B without code changes.

---

## Phased implementation

### Phase 0 — Scaffold `backend_v2/`
- `cp -r backend backend_v2`; delete `modules/simulation`, `modules/pdf_processing/{ai_extraction_service,image_generation_service}.py`, `common/services/simulation_helper/` (everything LangChain).
- `pyproject.toml`: drop `langchain*`, `langchain-postgres`, `langchain-experimental`; add `claude-agent-sdk`, `anthropic`, `google-genai`, `pgvector` (raw), `mcp`.
- Confirm `uv sync` succeeds and `uv run alembic upgrade heads` still works against the shared DB.

### Phase 1 — Shared AI plumbing
1. `common/services/embeddings_service.py` — thin `async def embed(texts) -> list[list[float]]` around the OpenAI SDK.
2. `common/services/pgvector_store.py` — direct SQL against existing `vector_embeddings` + `grading_material_chunks` tables. Functions: `similarity_search(query_embedding, namespace, k)`, `upsert(embedding, metadata)`. Replaces `PGVector` wrapper; same schema, no migration.
3. `common/services/image_service.py` — Gemini 2.5 Flash Image generation with a strategy pattern so OpenAI stays as fallback.
4. `common/config.py` — add `ANTHROPIC_API_KEY`, `GOOGLE_GENAI_API_KEY`, `PERSONA_MODEL`, `GRADING_MODEL`, `IMAGE_PROVIDER` settings.

### Phase 2 — MCP tool server (`modules/simulation/mcp/`)
Each tool is an `@tool`-decorated async function returning `{"content":[...], "is_error": bool}`. Assemble with `create_sdk_mcp_server(name="sim", version="1.0.0", tools=[...])`.

- **`recall_memory(persona_id, scene_id, query, k=5)`** → port of `scene_memory_service.py` hybrid retrieval; calls `pgvector_store.similarity_search`.
- **`lookup_rubric(scenario_id, query, k=3)`** → port of `grading_vector_store.py`.
- **`submit_grade(user_progress_id, scene_id, rubric_scores, strictness)`** → writes `scene_progress.grading_result` + `grading_materials` rows.
- **`advance_scene(user_progress_id)`** / **`complete_scene(user_progress_id, scene_id, summary)`** → state machine transitions (port from `core/scene_progression.py`).
- **`write_summary(user_progress_id, scene_id, summary_text)`** → writes `conversation_summaries`.
- **`extract_personas(pdf_text)`** / **`extract_scenes(pdf_text)`** / **`extract_objectives(pdf_text)`** → return structured JSON; orchestrator parses.

Every tool uses the existing SQLAlchemy repositories (`modules/simulation/repository.py`) so the DB layer stays untouched.

### Phase 3 — Persona runtime + ChatOrchestrator rewrite
- **`prompts/persona_system.py`**: port the `_BIG_FIVE_DESCRIPTORS` dict from `persona_agent.py:40-80` and the system-prompt template. No LangChain imports — plain string formatting that consumes `SimulationPersona` fields from `common/db/models/publishing/simulation.py:63-90`.
- **`persona_runtime.py`**:
  ```python
  async def run_persona_turn(persona, user_progress, user_message, session_id) -> AsyncIterator[str]:
      opts = ClaudeAgentOptions(
          model=settings.persona_model,
          system_prompt=build_persona_system_prompt(persona, scene_context),
          mcp_servers={"sim": sim_server},
          allowed_tools=["mcp__sim__recall_memory", "mcp__sim__lookup_rubric"],
          tools=[],  # no Read/Edit/Bash — personas aren't coders
          resume=session_id,
      )
      async for msg in query(prompt=user_message, options=opts):
          if isinstance(msg, AssistantMessage):
              for block in msg.content:
                  if isinstance(block, TextBlock): yield block.text
          elif isinstance(msg, ResultMessage):
              save_session_id(session_id or msg.session_id)
  ```
- **`orchestrator.py`**: thin state manager — loads `user_progress`, picks target persona, checks scene-completion preconditions, delegates to `persona_runtime`. No LLM calls here.
- **`handlers/chat_handler.py`**: FastAPI WebSocket/SSE endpoint that streams yielded text chunks to the client. Replaces `modules/simulation/handlers/chat_handler.py:41-80`.

### Phase 4 — Grading, summarization, PDF extraction
- `grading_agent.py` → one-shot `query()` using Haiku 4.5 + `grading_system.py` prompt + grading MCP tools. No agent loop needed for grading — `stop_on_first_result=True` pattern.
- `summarization_agent.py` → same shape, writes via `mcp__sim__write_summary`.
- `modules/pdf_processing/agent_extraction.py` → orchestrator-style `query()` driven by `extract_personas` / `extract_scenes` / `extract_objectives` tools. Replaces `ai_extraction_service.py`.

### Phase 5 — Image generation swap
- Port `image_generation_service.py` behavior (persona avatars, scene imagery) to `common/services/image_service.py` using `google-genai` → `gemini-2.5-flash-image`.
- Keep the OpenAI DALL·E path behind `IMAGE_PROVIDER=openai` so we can A/B.

### Phase 6 — Tests
- Reuse `backend/tests/` fixtures. Add:
  - Unit: persona prompt builder → snapshot test on Big Five permutations.
  - Unit: each MCP tool handler → pytest-asyncio, mocked DB session.
  - Integration: a full scene turn using Anthropic's [prompt caching test pattern] with a mocked Anthropic client — confirm `session_id` is persisted + resumed across turns.
  - Smoke: one live hit per model (guarded by `RUN_LIVE_TESTS=1`) so CI doesn't pay API costs.

### Phase 7 — Parity + cutover
- Run both backends against the same DB on different ports (`8000` old, `8001` new). Frontend env-flag `NEXT_PUBLIC_BACKEND=v2` flips which one it hits.
- Pick one scenario, run through end-to-end on both; diff grading scores + conversation quality.
- When green, rename `backend_v2 → backend`, archive the old tree on a branch.

---

## Critical files to read / reuse

| Purpose | File |
| --- | --- |
| Persona DB model | `backend/common/db/models/publishing/simulation.py:63-90` |
| Big Five prompt logic (port) | `backend/modules/simulation/agents/persona_agent.py:40-80` |
| Current orchestrator (reference) | `backend/modules/simulation/core/orchestrator.py:51-91` |
| Current memory retrieval (port) | `backend/common/services/simulation_helper/scene_memory_service.py` |
| Current grading RAG (port) | `backend/common/services/simulation_helper/grading_vector_store.py` |
| Scene state machine (port) | `backend/modules/simulation/core/scene_progression.py` |
| Chat handler shape (reference) | `backend/modules/simulation/handlers/chat_handler.py:41-80` |
| Shared DB (reuse verbatim) | `backend/common/db/**` |
| Alembic migrations (reuse) | `backend/migrations/**` |

No schema changes needed — the `agent_sessions`, `session_memory`, `vector_embeddings`, `conversation_logs`, `conversation_summaries`, `scene_progress`, and `grading_materials` tables all map cleanly onto the new runtime.

---

## Preserved API contract (the rewrite's non-negotiable surface)

The Next.js frontend hits the backend through a generic `/api/proxy/[...path]` passthrough plus a handful of dedicated Next routes. Every path below must keep its **method, path, auth mode, request shape, response shape, and status codes** after the rewrite. The inventory below is the full consumed surface — anything not listed here is internal and can change freely.

Conventions used in the tables:
- **Auth**: `anon` / `user` (JWT cookie) / `professor` / `student` / `admin`
- **I/O**: only the shape-critical fields; full Pydantic names live in the module's `schemas/dto.py`

### Auth (`/api/auth/users`)

| Method + Path | Auth | Request | Response |
| --- | --- | --- | --- |
| `POST /register` | anon | `UserRegister` | `UserResponse` + `access_token` cookie |
| `POST /login` | anon | `{email, password}` | `UserLoginResponse` + cookie |
| `POST /logout` | user | — | `{message}` + cookie cleared |
| `POST /forgot-password` | anon | `PasswordResetRequest` | `{message}` |
| `POST /check-email` | anon | `{email}` | `{exists: bool}` |
| `GET /status` | optional | — | `{authenticated: bool, user?}` |
| `GET /google/login` | anon | — | `{auth_url, state}` |
| `GET /google/callback` | anon | `?code&state` | 302 redirect |
| `POST /google/select-role` | anon | `RoleSelectionRequest` | `UserLoginResponse` |
| `POST /google/link` | anon | `AccountLinkingRequest` | `UserLoginResponse` |
| `GET /google/status/{state}` | anon | — | `{status, data?, link_required}` |
| **`PUT /users/me`** ⚠ | user | profile fields | `UserResponse` |
| **`POST /users/change-password`** ⚠ | user | `{current, new}` | `{message}` |

⚠ = consumed by the frontend (profile page) but not found in the backend router survey — see *Gaps* below.

### Simulation runtime (`/api/simulation`)

| Method + Path | Auth | Shape notes |
| --- | --- | --- |
| `POST /start` | user | `{simulation_id}` → `{user_progress_id, simulation, current_scene}` |
| `POST /linear-chat-stream` | user | **SSE** (`text/event-stream`, JSON chunks) *or* `202 {job_id}` under queue pressure |
| `POST /linear-chat` | user | non-streaming fallback (e.g. submit-for-grading) |
| `GET /scenes/{scene_id}` | user | `SimulationSceneResponse` |
| `POST /save-message` | user | writes `ConversationLog` — `session_id` required |
| `POST /execute-code` | user | Daytona sandbox execution |
| `GET /sandbox-state?user_progress_id=` | user | sandbox status poll |
| `GET /grade?user_progress_id=` | user | grade result or `202 {job_id}` |
| `GET /progress/{user_progress_id}` | user | `UserProgressResponse` |
| `GET /job/{job_id}/status` | user | queue status (ownership-checked) |
| `GET /job/{job_id}/result` | user | completed job result |
| `POST /api/stream-chat` | user | **alias** of `linear-chat-stream` — keep both paths alive |

**Streaming format** must stay identical: the frontend SSE parser consumes JSON chunks with `{type, content, persona_id?, scene_id?, ...}`. Agent SDK yields `AssistantMessage`/`TextBlock`/`ToolUseBlock`/`ResultMessage`; the rewrite's chat handler must translate those into the same SSE wire format.

### PDF processing (`/api/pdf-processing`)

| Method + Path | Auth | Notes |
| --- | --- | --- |
| `POST /parse-pdf-fast-autofill` | optional | multipart; quick persona extraction |
| `POST /parse-pdf` | optional | multipart; full pipeline |
| `POST /parse-pdf-with-progress` | optional | multipart; returns `{session_id}`, spawns async task |
| `GET /pdf-progress/{session_id}` | anon | polling fallback |
| `POST /pdf-progress/{session_id}/reset` | anon | clears state |
| `GET /get-default-personas/` | anon | static fallback |
| `GET /llamaparse-health/` | anon | debug |
| **`WS /ws/pdf-progress/{session_id}`** ⚠ | token | progress stream (not surfaced by backend survey — see *Gaps*) |

### Publishing (`/api/publishing/simulations`)

| Method + Path | Auth | Notes |
| --- | --- | --- |
| `GET /` (trailing slash required) | user | `?status=` filter |
| `GET /drafts/` | user | drafts list |
| `GET /drafts/{id}` | user | draft detail |
| `GET /{id}/full` | user | complete nested data |
| `GET /{id}/upload-status` | user | S3 image status |
| `POST /save` | user | upsert draft |
| `POST /publish/{id}` | user | publish workflow |
| `PUT /{id}/status` | user | draft/active/archived |
| `DELETE /{id}` | user | soft delete |
| **`WS /ws/{user_id}?token=`** | token | real-time publish status |

### Professor cohorts (`/professor/cohorts`)

GET/POST `/`, GET `/admin/all` (admin), GET/PUT/DELETE `/{cohort_unique_id}`, POST `/refresh-assignments`, GET `/{id}/students`, POST `/{id}/students`, PUT/DELETE `/{id}/students/{student_id}`, POST `/{id}/students/remove`, GET/POST `/{id}/simulations`, DELETE `/{id}/simulations/{assignment_id}`, GET `/{id}/completion-summary`, GET/POST `/{id}/invites`, DELETE `/{id}/invites/clear-expired`, DELETE `/{id}/invites/{invite_id}`, POST `/{id}/invite` (email), GET `/{id}/invitations` (list email invites).

### Professor grading (`/professor/grading`)

GET `/instances/{id}/submission`, GET `/instances/{id}/history`, POST `/instances/{id}/review`, POST `/instances/{id}/review/revert`, POST `/regrade/{user_progress_id}`, POST `/admin/regrade/{user_progress_id}` (admin).

### Student surface

`/student/cohorts`, `/student/cohorts/{id}/simulations`, `/student/invitations`, `/student/invitations/{id}/respond`, `/student/invitations/{token}` (anon), `/student/invitations/{token}/respond` (anon), `/student/notifications`, `/student/notifications/unread-count`, `/student/notifications/{id}/read`, `/student/notifications/mark-all-read`.

Student simulation instances (`/student-simulation-instances`): GET/POST `/`, GET/PUT `/{unique_id}`, GET `/assignment/{assignment_id}/instances`, POST `/{unique_id}/start-simulation`, POST `/{unique_id}/reset-simulation`, POST `/{unique_id}/start`, POST `/{unique_id}/complete`.

### Notifications (professor)

GET `/professor/notifications`, GET `/professor/notifications/unread-count`, POST `/professor/notifications/{id}/mark-read`, POST `/professor/notifications/mark-all-read`.

### Top-level invites (`/invites`, no `/api` prefix)

GET `/invites/{token}` (anon), POST `/invites/{token}/accept` (student).

### Messaging ⚠ (`/messages`)

Frontend consumes: GET/POST `/messages/`, GET `/messages/{id}`, POST `/messages/{id}/reply`, POST `/messages/{id}/mark-read`, GET `/messages/users/`, GET `/messages/cohorts/`. **Not found** in the backend router survey — see *Gaps*.

### Health

`GET /health` (anon) → `{status, version, database}`.

---

## Known contract gaps / discrepancies to resolve before rewrite

These are mismatches the two surveys uncovered that must be settled before (or during) the Agent-SDK rewrite — otherwise the frontend silently breaks.

1. **Messaging module** — frontend has a full `/messages/*` surface (thread list, send, reply, mark-read, user/cohort picklists) but the backend inventory found no such router. Action: grep for `messages` router mounting in `app/api/__init__.py` and `app/main.py`; if truly missing, either (a) the feature is dead-code on the frontend and can be removed from the rewrite scope, or (b) we need to spec + implement it fresh in `modules/messaging/`.
2. **PDF progress transport** — frontend opens `ws://…/ws/pdf-progress/{session_id}`; backend inventory only lists `GET /pdf-progress/{session_id}` polling. Action: verify whether a WebSocket route exists (likely in `app/main.py` at the app level, not a module router) and, if so, port it. If only polling exists, the frontend is paying for a WebSocket that never connects — either way we need to confirm the transport the rewrite must implement.
3. **Profile endpoints** — frontend calls `PUT /users/me` and `POST /users/change-password` from the profile page; neither appears in the auth inventory. Action: find them or spec them. The auth module is the right home.
4. **Email-invite endpoints** — frontend calls `POST /professor/cohorts/{id}/invite` (singular) and `GET /professor/cohorts/{id}/invitations`, which are distinct from the reusable `/invites` (plural) routes. The backend inventory lists the plural set but not the singular email-invite set. Action: confirm and document both.
5. **Trailing-slash sensitivity** — FastAPI treats `/foo` and `/foo/` as different URLs with the default router settings. The frontend proxy preserves whatever the caller used, so the rewrite must keep the exact same trailing-slash decisions (notably `/api/publishing/simulations/`, `/student-simulation-instances/`, `/messages/users/`, `/messages/cohorts/`).

Ultraplan should treat items 1–4 as must-resolve blockers; item 5 is a lint-level guardrail.

---

## Test strategy

The rewrite's test pyramid: **contract tests** guard the frontend-visible API shape; **unit tests** pin individual services, tools, and prompt builders; **integration tests** exercise full request → DB → MCP-tool → response paths with a mocked Anthropic client. Live-API smoke tests are opt-in and not run in CI.

### 1. Contract tests (the safety net for the frontend)

One `tests/contract/<module>/test_<endpoint>.py` file per endpoint in the *Preserved API contract* section, for **every** endpoint listed above (~70 endpoints). Each test asserts:
- status code for the happy path;
- status codes for each validation / auth / not-found branch;
- response body **shape** — validated against a frozen JSON schema snapshot (use `jsonschema` or `pydantic` models imported from the rewrite's `dto.py`);
- response **headers** the frontend depends on (e.g. `Set-Cookie: access_token` on login, `Content-Type: text/event-stream` on streaming chat);
- for streaming endpoints: the first N chunks decode into the expected `{type, content, ...}` envelope, and the final chunk is a terminator.

These tests run against both `backend/` (legacy) and `backend_v2/` (rewrite) in CI to prove parity. A shared pytest fixture `client_legacy` / `client_v2` switches the target; identical assertions pass against both.

### 2. Unit tests (per module)

| Area | What to pin |
| --- | --- |
| `prompts/persona_system.py` | Snapshot test: 8 Big Five trait combinations → rendered system prompt string is byte-stable. |
| `prompts/grading_system.py`, `summarization_system.py` | Snapshot tests with representative inputs. |
| `persona_runtime.py` | With a mocked `query()` returning a scripted `[AssistantMessage(...), ResultMessage(session_id="abc")]`, assert (a) session id is persisted to `agent_sessions`, (b) on a second call `resume=` is set, (c) streamed chunks are yielded in order. |
| Each MCP tool handler | pytest-asyncio; mocked `db_session` + `pgvector_store`; assert return shape matches MCP `{content, is_error?}` contract and that `is_error=True` is returned on expected failure modes (missing row, bad args) rather than raising. |
| `pgvector_store.similarity_search` | Against a SQLite-in-memory-with-pgvector-stub or a real dockerized Postgres fixture; insert 5 embeddings, query, assert ordering. |
| `embeddings_service.embed` | Mock OpenAI client; assert request shape + retries on 429. |
| `image_service` | Mock Gemini and OpenAI clients; assert strategy switch via `IMAGE_PROVIDER` env. |
| Auth utilities (copied verbatim) | Reuse existing tests from `backend/tests/modules/auth/`. |

### 3. Integration tests

- **One-scene happy path**: register → login → start simulation → 3 chat turns → advance scene → grade. Mock Anthropic with a `FakeClaudeClient` that returns scripted `AssistantMessage` sequences. Assert: `conversation_logs` has 6 rows (3 user + 3 assistant), `agent_sessions.session_id` is stable across turns, `scene_progress.grading_result` is populated after grading, `conversation_summaries` has one row after scene completion.
- **Scene transition & tool-call loop**: scripted Claude response calls `mcp__sim__recall_memory` then `mcp__sim__complete_scene`; assert both tool handlers executed and DB mutations landed.
- **PDF extraction**: upload fixture PDF → assert `SimulationPersona` + `SimulationScene` rows created with expected fields.
- **Queue fallback**: simulate Anthropic rate-limit error → assert chat endpoint returns `202 {job_id}`, job appears in Redis, polling `/job/{job_id}/status` returns `completed` with the result after the worker processes it.

### 4. Frontend compatibility tests (optional, recommended)

Stand up `backend_v2` on `:8001`, point a Playwright run of the existing frontend at it, and exercise: login, create cohort, enroll student, run one simulation scene, grade it. Green run = rewrite is frontend-safe.

### 5. Live smoke tests (manual / opt-in)

Guarded by `RUN_LIVE_TESTS=1`. One hit per model per provider to catch credential or model-ID drift. Not run in CI.

### Test infrastructure additions

- `tests/fake_claude.py` — `FakeClaudeClient` that implements the subset of `claude_agent_sdk.query` the rewrite uses, with scriptable responses.
- `tests/contract/conftest.py` — dual-target fixture (legacy vs v2).
- `tests/fixtures/pdfs/` — 1-2 anonymized case study PDFs for extraction tests.
- `tests/fixtures/scenarios/` — JSON fixtures of canonical scenarios, personas, scenes.

---

## Open questions / assumptions locked in

- **Auth, cohorts, notifications, professor, student, publishing routers** are copied unchanged — they have no AI surface area.
- **Embeddings stay on OpenAI `text-embedding-3-small`** to avoid re-embedding existing `vector_embeddings` rows. Switching to Voyage is a separate migration.
- **Daytona sandbox** (`sandbox_service.py`) untouched — code-challenge runtime is orthogonal.
- **Redis caching**: Agent SDK has its own prompt caching; we drop LangChain's Redis-backed LLM cache but keep Redis for session metadata / rate limiting.

---

## Verification

1. `cd backend_v2 && uv sync && uv run alembic upgrade heads` — clean install, schema up.
2. `uv run pytest tests/ -v` — all copied + new tests pass.
3. `uv run uvicorn app.main:app --reload --port 8001` — server boots.
4. Live smoke (requires `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_GENAI_API_KEY`):
   - Register a student, enroll in a fixture scenario.
   - POST a user message to the chat endpoint; confirm streamed Claude response.
   - Confirm `agent_sessions.session_id` is populated and reused on turn 2.
   - Trigger scene completion; confirm `scene_progress.grading_result` + `conversation_summaries` rows appear.
   - Upload a case-study PDF; confirm `extract_personas` / `extract_scenes` tool calls fire and produce valid `SimulationPersona` rows.
5. Parity check: run the same scenario on `backend` (:8000) and `backend_v2` (:8001); compare transcripts + grading for regressions.
