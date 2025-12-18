Goal
Identify and fix the real root causes of your Railway crashes under 50+ concurrent simulation users (especially Neon DB connection errors) and evolve the backend so it can scale (within the current stack) to hundreds–thousands of concurrent students, while following the architecture.md standards.
What I found in your current codebase
Architecture alignment with your description
The monolithic api/simulation.py referenced in architecture.md has been refactored into modules/simulation/* with a thin router in [backend/modules/simulation/router.py](backend/modules/simulation/router.py) and a service layer in [backend/modules/simulation/service.py](backend/modules/simulation/service.py).
linear-chat and linear-chat-stream are now clean async endpoints wired via app/routers/simulation.py to modules/simulation.router, consistent with the “thin router, fat service” guideline.
Database connection pooling (critical Neon interaction)
Your main SQLAlchemy engine is configured in [backend/common/db/core.py](backend/common/db/core.py) with aggressive pooling:
core.pyLines 21-41
)
    _engine_kwargs = {        "future": True,        "echo": sqlalchemy_echo,        "pool_pre_ping": True,    }    if settings.database_url.startswith("postgresql"):        _engine_kwargs.update({            "pool_size": 70,            "max_overflow": 80,            "pool_recycle": 300,            "pool_timeout": 30,            "connect_args": {"connect_timeout": 10, "application_name": "n-aible_Backend"},        })    engine = create_engine(settings.database_url, **_engine_kwargs)
This allows up to 150 client connections from a single Railway app instance, before counting:
Connections created by PGVector (LangChain PGVector in langchain_service.py) which uses its own engine and pool.
Extra SessionLocal() usages from persona callbacks and vectorstore maintenance.
Neon’s free/pooled setups typically allow ~100 server connections; with PgBouncer, Neon explicitly recommends avoiding large client-side pools and letting PgBouncer handle pooling. Your current config can therefore:
Exceed Neon's max_connections or PgBouncer pool size during spikes.
Trigger errors like “too many connections” / “remaining connection slots are reserved” and cause request failures and restarts on Railway.
Simulation endpoints and streaming behavior
router.pyLines 47-81
  @router.post("/linear-chat-stream")  async def linear_chat_stream(...):      service = SimulationService(db)      async def generate_stream():          async for chunk in service.stream_chat_message(...):              yield chunk      return StreamingResponse(          generate_stream(),          media_type="text/event-stream",          headers={...},      )
linear-chat-stream is implemented as a proper async SSE stream.
The router is thin and delegates to SimulationService, which in turn uses ChatHandler and the repository layer, matching architecture.md.
Each streaming request:
Loads and mutates DB state (via SimulationRepository and UserProgress, ConversationLog).
May invoke LangChain agents for personas, which call OpenAI and PGVector.
This means each open SSE stream typically holds onto:
At least one SQLAlchemy session (via FastAPI get_db) until the stream ends.
At least one OpenAI ChatOpenAI call (via LangChain) and several PGVector queries per user message.
AI calls and LangChain / OpenAI behavior
persona_agent.pyLines 568-657
  async def chat(...):      ...      response = await self.agent_executor.ainvoke(          {"input": message},          callbacks=[callback_handler],      )
Persona messages use LangChain’s async agent executor and ChatOpenAI with streaming=True. This is network‑bound async I/O and works well with FastAPI/uvicorn.
There is no global semaphore in the simulation module limiting concurrent OpenAI calls anymore (unlike the older simulation.py). Concurrency is now governed by:
The number of concurrent HTTP requests to /linear-chat-stream,
The number of persona agents engaged per message.
LangChainManager centralizes LLM, embeddings, and PGVector setup in common/services, which is aligned with the shared-infrastructure pattern in architecture.md.
PGVector usage and hidden DB load
PGVector is actively used as a semantic store:
langchain_service.pyLines 17-45
_vectorstore
    from langchain_postgres import PGVector    ...    class LangChainManager:        @property        def vectorstore(self):            if self._vectorstore is None:                self._vectorstore = PGVector(                    connection=settings.postgres_url,                    embeddings=self.embeddings,                    collection_name=settings.vector_collection_name,                    use_jsonb=True                )            return self._vectorstore
memory_service and PersonaAgent use PGVector to:
Store scene context, persona conversation history, persona knowledge, and user/assistant messages as embeddings.
Retrieve memories and context via similarity_search.
ChatOrchestrator uses PGVector for scene context storage (store_scene_context).
PGVector operates through its own SQLAlchemy engine/pool against Neon. So in addition to the main app engine pool, you have:
A separate PGVector pool,
Plus extra SessionLocal() calls in:
PersonaAgent._log_conversation,
PersonaAgent._load_conversation_history_into_memory,
Orchestrator helpers (_get_scene_personas, _get_persona_from_db).
There is also a direct SQL deletion against the PGVector embeddings table to clear persona conversation history; it’s technically safe (parameterized) but should be a rare cleanup action, not part of the per-message hot path.
Net result: during a load spike, your effective total connections to Neon can significantly exceed 150, across the main engine + PGVector + ad‑hoc sessions.
Runtime and deployment configuration on Railway
Railway uses uvicorn app.main:app with a single process (no explicit --workers), as seen in [backend_railway.toml](backend_railway.toml):
Concurrency is limited by what one async event loop can handle effectively.
Any latency from DB connection waits or Neon rejections directly inflates response times and can pile up open SSE streams.
Restart policy is on_failure with up to 5 retries; repeated DB connection failures or unhandled exceptions under high load can therefore look like “the platform crashed” to users.
DB access patterns in simulation (session hygiene)
modules/simulation/repository.py is clean and uses ORM queries per architecture.md (repositories own DB access).
However, some hot-path helpers bypass the request-scoped Session and open their own sessions with SessionLocal():
ChatOrchestrator._get_scene_personas and _get_persona_from_db,
PersonaAgent._log_conversation and _load_conversation_history_into_memory.
That means:
Each streaming request can use multiple DB connections, not just the one injected into SimulationService.
Combined with PGVector’s engine, this amplifies Neon connection usage.
How this maps to your hypotheses
1. Thread Pool Limitation (6 workers) & 2. AI Call Semaphore (3 max)
Those limits existed in your previous monolithic simulation.py; in the current refactored code they are no longer present in modules/simulation.
You now rely on:
Async FastAPI endpoints and async LangChain ainvoke.
No central semaphore for OpenAI calls in the simulation stack.
Historically, a 6‑worker executor + only 3 concurrent AI calls for 50+ users would absolutely cause queuing and timeouts, so your initial diagnosis for the beta test period was reasonable.
Today, the larger bottleneck is Neon connection limits and PGVector activity, not an explicit thread pool cap.
3. Synchronous OpenAI calls inside async endpoints
In the current implementation, persona chat uses async LangChain; the main simulation endpoints and handlers are async, and there is no synchronous OpenAI client usage inside these endpoints.
This specific issue has effectively been mitigated in the new architecture.
4. Database Connection Exhaustion
This is strongly supported by the code and Neon’s documented limits:
App engine pool up to 150 connections.
PGVector with its own pool, plus extra SessionLocal() invocations.
Neon free/standard tiers with ~100 server connections, and PgBouncer recommending small or no client-side pooling.
Under 50+ concurrent students, each sending multiple messages and hitting PGVector and the ORM, it’s very likely you:
Exceeded Neon’s connection limits, causing connection errors.
Triggered timeouts waiting for pool_timeout=30 in SQLAlchemy.
This aligns directly with the “database connection error” you saw in Railway logs and is almost certainly one of the main crash causes.
5. Streaming Connection Overload
/linear-chat-stream keeps SSE connections open, but the implementation itself is non‑blocking and uses small asyncio.sleep calls, which is fine on Uvicorn.
The problem is that each stream is tightly coupled to heavy DB + PGVector work and at least one OpenAI call. With many students:
Long‑lived SSE connections accumulate while waiting on Neon and OpenAI.
If Neon starts refusing connections or becomes slow, SSE handlers stall and pile up, increasing memory and CPU usage until Railway restarts the app.
Streaming is not “wrong,” but it amplifies the impact of DB and AI bottlenecks.
Additional likely contributors beyond your list
Overly large SQLAlchemy pool for a PgBouncer‑fronted Neon DB
Neon's docs recommend avoiding big client pools when using the pooled connection string; instead you should:
Use a small pool_size (e.g., 5–10) and max_overflow (e.g., 5–10), or
Use NullPool when connecting to the pooled endpoint so PgBouncer alone manages pooling.
Your current config (150 possible connections) contradicts that guidance and is fragile in production.
Double‑pooling via PGVector
LangChain’s PGVector instantiates its own SQLAlchemy engine (with default pooling) against the same Neon DB.
That means you effectively have two independent connection pools (main app + vectorstore) competing for Neon’s limited connections.
Per‑request session usage patterns
Persona logging and some orchestrator helpers use new SessionLocal() instances instead of reusing the request‑scoped session.
This increases the number of distinct connections opened and briefly held per persona interaction.
Single Uvicorn worker on Railway
With one process, any backlog (waiting for DB connections or AI responses) accumulates in that single event loop.
If memory spikes (e.g., many active LangChain graphs and PGVector results), Railway may OOM‑kill or restart the process.
PGVector load characteristics
PGVector is conceptually the right tool for semantic memory, but:
Frequent add_texts + similarity_search for each message,
Plus occasional direct bulk deletions of embeddings,
All through a separate engine,
Make it a major contributor to DB load, especially when conversations are not yet huge.
In its current form, PGVector usage is more about richer context and features than pure speed, and must be tuned and bounded so it doesn’t overwhelm Neon under high concurrency.
Concrete next steps (what I recommend doing)
All of these will be implemented following architecture.md: keep routers thin, put business logic in services, keep DB access in repositories or well-scoped infrastructure modules, and avoid new raw SQL except where absolutely necessary and isolated.
1. DB Connection & Neon Alignment
Right-size SQLAlchemy pooling for Neon
Update [backend/common/db/core.py](backend/common/db/core.py) so that when DATABASE_URL points to Neon:
Use pool_size ≈ 5–10 and max_overflow ≈ 5–10, or
Use NullPool if you are using Neon’s pooled connection string (PGBOUNCER endpoint), letting PgBouncer manage pooling.
Keep pool_pre_ping=True and moderate pool_timeout (e.g., 5–10s) to avoid long stalls.
Align PGVector’s engine with Neon
Ensure the PGVector instance created in langchain_service.py uses:
A single shared vectorstore instance (LangChainManager.vectorstore),
A very small pool or NullPool when targeting the pooled Neon endpoint.
Do not create additional PGVector engines elsewhere.
Document connection strategy
In common/config.py / env conventions:
Clearly differentiate direct vs pooled Neon URLs.
Ensure settings.database_url and LangChainSettings.postgres_url point to the intended endpoint.
This keeps future changes aligned with Neon’s guidance.
2. Simulation AI & Streaming Concurrency Controls
Global async semaphores (app-level)
Introduce a small concurrency management module (e.g. common/utils/concurrency.py) that provides process-wide asyncio.Semaphore instances for:
Persona agent executions (LangChain calls),
Active streaming chat sessions.
In SimulationService and/or ChatHandler, wrap:
Persona chat_with_persona_langchain calls,
stream_chat_message/linear-chat-stream handling,
Inside async with semaphore: blocks so you cap heavy AI/DB work per process.
Start with conservative limits (e.g. 20–40 concurrent persona calls per process) and adjust after load testing.
Back-pressure for /linear-chat-stream
Before starting the main streaming work, check capacity:
If at capacity, return 429 or 503 with a clear JSON error instead of attempting work that will almost certainly fail or stall.
Optionally add per-user limits (e.g. max N concurrent streams per user) to prevent a single client from monopolizing resources.
Keep routers thin
Implement these controls at the service/handler layer, not directly in the router, so app/routers remains a “wiring” layer per architecture.md.
3. DB Session Usage Hygiene in Simulation
Unify DB access per request
Refactor modules/simulation so that hot paths:
Use the request-scoped Session injected via get_db into SimulationService,
Or go through SimulationRepository.
Specifically:
Replace SessionLocal() usage in ChatOrchestrator._get_scene_personas and _get_persona_from_db with repository calls (or injected sessions).
Replace SessionLocal() in PersonaAgent._log_conversation and _load_conversation_history_into_memory with patterns that either:
Reuse the request-scoped session when the agent is used within an HTTP request, or
Use a small, controlled session only in non-hot paths (e.g., background tasks).
Bounded conversation history for memory
When loading conversation history into persona memory:
Limit the number of messages (e.g., last N messages per scene),
Optionally summarize or compress older history instead of loading everything.
This reduces both:
ORM query cost,
Vectorstore writes and reads.
PGVector deletion frequency
Keep the direct SQL deletion against PGVector’s embeddings table as a mechanism, but:
Use it as a rare cleanup operation (e.g., when resetting simulations or clearing old sessions),
Move it out of the per-message hot path (potentially into a background job).
4. PGVector Tuning and Scope
Tune existing PGVector usage
Continue using PGVector for:
Persona semantic memory and knowledge,
Scene/context storage where it clearly improves educational experience.
But:
Avoid embedding every single message if it doesn’t materially change behavior.
Consider only embedding:
Student messages that are meaningful for grading,
Important persona responses,
Key scene summaries.
Use reasonable caps (e.g., max N embeddings per scene/user) and consider pruning or summarizing older entries.
Be selective with new PGVector use cases
Add PGVector-based features only when they replace heavier work (e.g., repeated large LLM summarizations or scanning big tables), such as:
Grading support where you need to search large corpora of rubrics or past responses,
Case-study search where underlying text is large.
Implement new usage via dedicated services in common/services or modules/*/services (per architecture.md), not directly in routers.
5. Load Testing and Observability
Structured logging & metrics
Enhance logging around:
DB pool usage (you already log stats in log_checkout; ensure they are visible and parsable in production logs),
Rejected connections and SQLAlchemy TimeoutError from the pool,
AI semaphore utilization (how often you hit capacity),
SSE stream counts and durations.
Keep logging within the patterns described in common/logging.py / architecture.md (structured, no noisy prints in production).
Load testing scenario
Create a simple test scenario (Locust, k6, or similar) that simulates 50–100 (eventually 500+) concurrent students hitting /api/simulation/linear-chat-stream with realistic behavior:
Each “student” sends a message every few seconds,
Uses a mix of general orchestrator messages and persona @mentions.
Measure:
Neon connection usage vs. configured limits,
Pool wait times and timeouts,
Error rates (429, 503, 5xx),
End-to-end latency percentiles (p50/p95/p99).
6. Railway Runtime Tuning
Worker and replica strategy
After fixing DB pooling and adding concurrency/back-pressure:
Consider running 2–3 Uvicorn workers if your Railway plan allows the memory/CPU,
Or keeping 1 worker but relying more on semaphores and DB limits to cap effective concurrency.
When ready to scale to many more concurrent students:
Increase numReplicas in backend_railway.toml,
Use Redis-backed global limits (for AI calls and SSE streams) so multiple replicas share the same safety caps.
These changes keep your design aligned with architecture.md (feature-based modules, thin routers, services + repositories, shared infrastructure in common/*) while directly addressing the real bottlenecks: Neon connection exhaustion, unbounded AI/streaming concurrency, PGVector’s double-pooling, and extra session usage in the simulation module.