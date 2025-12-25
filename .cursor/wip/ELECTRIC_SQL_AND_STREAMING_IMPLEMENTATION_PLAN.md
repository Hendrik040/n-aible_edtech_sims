# ElectricSQL + “More Streaming” Implementation Plan
> **Created:** Dec 25, 2025  
> **Scope:** Add ElectricSQL for realtime DB sync + expand true streaming (token-level) in chat.  
> **Principle:** **SSE/WebSocket for ephemeral streams (tokens/progress)**, **Electric for persisted state (messages/progress/status)**.

---

## Goals
- **ElectricSQL**: Make key app state realtime/offline-capable in the UI (conversation logs, progress, notifications, publishing/upload status) without polling.
- **More streaming**: Finish **true token streaming** for persona chat (no fake char-by-char delays), and keep the UI responsive while persistence happens in the background.
- **Minimal surface area**: Add the smallest set of tables/shapes and the smallest number of new endpoints required.

## Non-goals (for first iteration)
- Replace all existing REST endpoints.
- Full offline-first across every screen.
- Multi-writer conflict-heavy workflows (scenario builder live-collab, etc.). Keep Electric scope mostly **read + append** first.

---

## Target Architecture
### What goes over Electric vs SSE
- **SSE (existing)**: `POST /api/simulation/linear-chat-stream`
  - Streams tokens (TTFB/UX).
  - Emits “thinking/tool” events if needed.
- **ElectricSQL**:
  - Syncs **persisted** rows that back the UI:
    - `conversation_logs` (authoritative chat history)
    - `user_progress` + `scene_progress` (progress UI)
    - `notifications` (student/professor notifications)
    - publishing/image status tables (whatever the current source-of-truth is)

### Why this split works
- Token streams are **ephemeral** and high-frequency; Electric is best at syncing **stored facts**.
- After the stream ends, the final assistant message is saved; Electric pushes that row to any other tabs/devices automatically.

---

## Data model prerequisites (Postgres)
Electric relies on logical replication. Also, for safe syncing and client-side merges, tables should have:
- **Primary key** (required)
- **`updated_at`** timestamp (recommended)
- Optional: **soft delete** marker if you need deletes to propagate (e.g. `deleted_at`)

**Plan (minimal changes):**
- If any target table lacks `updated_at`, add it (server-managed).
- Prefer append-only semantics for `conversation_logs` (already fits).

---

## Electric deployment options
### Option A (recommended): Self-host Electric sync service
- Run Electric as a separate service next to the backend.
- Connect it to the same Postgres.
- Configure auth + shapes.

### Option B: Electric Cloud
- Same client integration; fewer ops tasks.
- Still requires shape/auth integration.

**Either way**, you need:
- A **DATABASE_URL** with permission for logical replication (or the provider’s required setup).
- A stable **ELECTRIC_URL** reachable from the frontend.

---

## Security / tenancy model (critical)
Electric must not let users sync other users’ rows.

### The model to implement
- Backend issues a short-lived **Electric auth token** derived from the user’s session.
- Shapes are defined with **server-side filters** using claims from that token (e.g. `user_id`, `role`, `cohort_ids`).

### Pseudocode (auth token)
```text
function electric_token_endpoint(current_user):
  claims = {
    sub: current_user.id,
    role: current_user.role,
    // optional: cohort_ids, professor_id, etc.
    exp: now + 10 minutes
  }
  return sign(claims, ELECTRIC_AUTH_SECRET)
```

### Pseudocode (shape definition pattern)
```text
shape "conversation_for_progress":
  sql: select * from conversation_logs
       where user_progress_id = $progress_id
         and user_id = $sub   // or join through user_progress -> user_id
```

**Rule:** Every shape must be provably scoped by auth claims.

---

## Shape design (MVP)
Start with 3–5 shapes that unlock real UX wins.

### 1) Conversation history (authoritative)
- **Purpose**: Realtime chat history updates (esp. across tabs/devices).
- **Shape key**: `user_progress_id` (and `scene_id` if you want smaller scopes).

### 2) Current progress + scene state
- **Purpose**: Progress UI updates immediately (scene completion, turn count, etc.).
- **Shape key**: `user_progress_id`.

### 3) Notifications
- **Purpose**: Live notification bell/badges.
- **Shape key**: `user_id`.

### 4) Publishing / upload status (if needed)
- **Purpose**: Professor sees “image upload status” without polling.
- **Shape key**: `scenario_id` scoped by professor ownership.

---

## Frontend integration plan (Next.js 15)
### Minimal client wiring
- Add an `ElectricProvider` (client component) that:
  - fetches Electric token from backend
  - initializes Electric client with `ELECTRIC_URL`
  - exposes a typed API (or simple hooks) for subscribing to shapes

### UI data flow (chat page)
**During a chat send:**
1. UI starts SSE request to `linear-chat-stream`
2. UI renders incoming tokens immediately
3. When stream finishes:
   - UI can either:
     - keep the final message already rendered, and later reconcile with the persisted row from Electric, or
     - replace the streamed “temp message” with the Electric-backed message once it arrives

### Pseudocode (chat UI reconciliation)
```text
onSend(message):
  tempId = createLocalTempAssistantMessage()
  stream = startSSE()
  for token in stream:
    appendToken(tempId, token)
  // backend persists final ConversationLog row
  // Electric sync delivers row -> replace tempId with real row id
```

---

## Backend integration plan (FastAPI)
### 1) Add Electric auth endpoint
- New endpoint: `GET /api/electric/token`
- Uses existing auth (`get_current_user()`)
- Returns a signed token for Electric

### 2) Define/host Electric shapes
Where this lives depends on Electric deployment:
- If Electric has its own config/shapes:
  - add shape definitions there
- If shapes are configured via a service file in-repo:
  - keep them in a dedicated location, e.g. `backend/electric/` (one small module)

### 3) Keep existing streaming endpoints
- Do not remove `linear-chat-stream`.
- Implement true token streaming per existing plan (`astream_events`) and remove artificial sleeps.

---

## “More streaming” (token-level) plan (ties to existing doc)
You already have a detailed blueprint in:
- `.cursor/wip/TRUE_STREAMING_IMPLEMENTATION_PLAN.md`

**MVP delta to implement:**
- Replace `AgentExecutor.ainvoke()` with `agent_executor.astream_events(..., version="v2")`
- Stream `on_chat_model_stream` chunks directly to SSE
- Save final assistant message once streaming completes (or accumulate in handler)

**Nice-to-have stream events:**
- `on_tool_start` / `on_tool_end` -> emit SSE “status” events so UI can show “using tool…”

---

## Rollout plan (small, safe increments)
### Phase 0: Infra readiness
- Confirm Postgres supports logical replication (provider-specific).
- Deploy Electric service (or enable Electric Cloud).
- Add `ELECTRIC_URL` + `ELECTRIC_AUTH_SECRET`.

### Phase 1: Electric auth + 1 read-only shape
- Implement `/api/electric/token`.
- Create **read-only** shape for `conversation_logs` scoped by `user_progress_id`.
- On chat page: subscribe and render history via Electric (fallback to existing REST if Electric unavailable).

### Phase 2: True token streaming (TTFB win)
- Implement true streaming in backend per existing plan.
- UI uses SSE for token streaming; Electric for persisted history.

### Phase 3: Progress + notifications shapes
- Add shapes for `user_progress`/`scene_progress`, `notifications`.
- Replace polling/refresh paths in the UI.

### Phase 4: Publishing/upload status
- Add shape for status and update professor dashboard to subscribe.

---

## Testing plan
### Backend
- **Auth**: token endpoint returns only for logged-in users; rejects anonymous.
- **Shape scoping**: attempt to access another user’s shape must fail / return empty.
- **Streaming**: first token arrives quickly; response is persisted.

### Frontend
- Chat renders tokens while stream runs.
- After completion, the persisted message arrives via Electric and reconciles correctly.
- Multi-tab: send message in tab A, tab B updates without refresh.

---

## Operational notes / gotchas
- **Logical replication** may require:
  - publication/replication slot setup
  - permissions that some managed Postgres tiers restrict
- **RLS**: If you already use Postgres RLS, decide whether Electric relies on it or on shape filters (don’t assume both).
- **Backfill & limits**: shapes should be bounded (e.g., last N messages) if tables are large.

---

## Deliverables checklist (what “done” looks like)
- [ ] Electric service reachable (dev + prod)
- [ ] `GET /api/electric/token` works and is scoped
- [ ] Chat history renders from Electric shape
- [ ] True token streaming enabled (no artificial delays)
- [ ] Electric reconciles persisted assistant messages after streaming
- [ ] Progress + notifications shapes (optional in MVP, required for “more realtime”)

