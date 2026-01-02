# E2E Streaming Test - Visual Map & Explanation

## 📋 Table of Contents
1. [Overview](#overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Class Structure](#class-structure)
4. [Execution Flow](#execution-flow)
5. [State Management](#state-management)
6. [Streaming Mechanism](#streaming-mechanism)
7. [Task System](#task-system)
8. [Event Lifecycle](#event-lifecycle)

---

## Overview

This test simulates **real user behavior** with **streaming responses** (SSE - Server-Sent Events). It measures:
- **TTFB** (Time To First Byte): When user sees the first response chunk
- **Total Time**: When entire stream is consumed
- **Realistic load**: Actually consumes the stream (not just fires requests)

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    LOCUST FRAMEWORK                              │
│  - Spawns multiple E2EStreamingUser instances                   │
│  - Manages concurrent execution                                 │
│  - Collects statistics                                          │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              E2EStreamingUser (Per User Instance)                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  User State:                                              │  │
│  │  - user_number: int                                       │  │
│  │  - access_token: str                                      │  │
│  │  - user_progress_id: int                                  │  │
│  │  - current_scene_id: int                                   │  │
│  │  - simulation_started: bool                                │  │
│  │  - messages_sent: int                                     │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Lifecycle Methods:                                       │  │
│  │  1. on_start() → Login + Start Simulation                │  │
│  │  2. @task methods → Execute during test                  │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    BACKEND API                                   │
│  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────┐ │
│  │  /api/auth/      │  │  /api/simulation/ │  │  /api/      │ │
│  │  users/login     │  │  start            │  │  simulation/│ │
│  │                 │  │                  │  │  linear-     │ │
│  │  Returns:        │  │  Returns:         │  │  chat-stream│ │
│  │  access_token    │  │  user_progress_id │  │             │ │
│  │                  │  │  current_scene_id │  │  Returns:   │ │
│  │                  │  │                   │  │  SSE Stream │ │
│  └──────────────────┘  └──────────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Class Structure

```
E2EStreamingUser (HttpUser)
│
├── Class Variables (Configuration)
│   ├── wait_time: between(5s, 15s)  # Random wait between requests
│   └── host: config.base_url        # Target server URL
│
├── Instance Variables (User State)
│   ├── user_number: int              # Unique ID (1-100)
│   ├── email: str                     # loadtest_user_1@test.com
│   ├── access_token: Optional[str]   # JWT token from login
│   ├── user_progress_id: Optional[int] # Simulation session ID
│   ├── current_scene_id: Optional[int] # Current scene in simulation
│   ├── simulation_started: bool        # Has simulation been started?
│   ├── messages_sent: int              # Counter for messages
│   └── max_messages_per_session: 10   # Restart after 10 messages
│
├── Constants
│   └── SAMPLE_MESSAGES: [10 messages] # Pre-defined chat messages
│
├── Lifecycle Methods
│   ├── on_start()                     # Called once per user
│   │   ├── Assign user_number
│   │   ├── Generate email
│   │   ├── _login()
│   │   └── _start_simulation()
│   │
│   └── @task methods                  # Called repeatedly during test
│       ├── send_begin_message()       # Weight: 1
│       └── send_chat_message()         # Weight: 10
│
└── Helper Methods
    ├── _login() → bool
    ├── _get_headers() → dict
    ├── _start_simulation() → void
    └── _send_streaming_message() → bool
```

---

## Execution Flow

### Phase 1: User Initialization (on_start)

```
┌─────────────────────────────────────────────────────────────┐
│  Locust spawns new E2EStreamingUser instance                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  on_start() called                                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  1. user_number = random(1, 100)                      │  │
│  │  2. email = "loadtest_user_{user_number}@test.com"    │  │
│  └───────────────────────────────────────────────────────┘  │
│                            │                                  │
│                            ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  _login()                                              │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  POST /api/auth/users/login                     │  │  │
│  │  │  Body: {email, password}                        │  │  │
│  │  │  ─────────────────────────────────────────────  │  │  │
│  │  │  Response: {access_token: "jwt..."}            │  │  │
│  │  │  ─────────────────────────────────────────────  │  │  │
│  │  │  Store: self.access_token = token               │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                            │                                  │
│                            ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  _start_simulation()                                  │  │
│  │  ┌─────────────────────────────────────────────────┐  │  │
│  │  │  POST /api/simulation/start                     │  │  │
│  │  │  Headers: Authorization: Bearer {token}         │  │  │
│  │  │  Body: {simulation_id}                       │  │  │
│  │  │  ─────────────────────────────────────────────  │  │  │
│  │  │  Response: {                                    │  │  │
│  │  │    user_progress_id: 123,                       │  │  │
│  │  │    current_scene: {id: 456}                     │  │  │
│  │  │  }                                              │  │  │
│  │  │  ─────────────────────────────────────────────  │  │  │
│  │  │  Store:                                         │  │  │
│  │  │    self.user_progress_id = 123                  │  │  │
│  │  │    self.current_scene_id = 456                  │  │  │
│  │  │    self.simulation_started = True               │  │  │
│  │  └─────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
│                            │                                  │
│                            ▼                                  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  User ready! Now enters task loop                     │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Phase 2: Task Execution Loop

```
┌─────────────────────────────────────────────────────────────┐
│  Locust Task Loop (runs continuously)                       │
│                                                              │
│  For each iteration:                                         │
│  1. Wait random(5-15 seconds)                               │
│  2. Pick task based on weights:                             │
│     - send_begin_message: 1/11 chance                       │
│     - send_chat_message: 10/11 chance                       │
│  3. Execute task                                            │
│  4. Repeat                                                  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌───────────────────────┐          ┌───────────────────────┐
│ send_begin_message()  │          │ send_chat_message()    │
│ Weight: 1             │          │ Weight: 10            │
│                       │          │                       │
│ Checks:               │          │ Checks:               │
│ - Has token?          │          │ - Has token?          │
│ - Simulation started?│          │ - Simulation started? │
│ - messages_sent == 0?│          │ - messages_sent == 0? │
│                       │          │   → Call begin first   │
│ If all true:          │          │ - messages_sent >= 10?│
│   Send "begin"        │          │   → Restart simulation│
│   messages_sent++     │          │                       │
│                       │          │ If all good:          │
│                       │          │   Pick random message │
│                       │          │   Send message        │
│                       │          │   messages_sent++     │
└───────────────────────┘          └───────────────────────┘
        │                                       │
        └───────────────────┬───────────────────┘
                            │
                            ▼
            ┌───────────────────────────────┐
            │  _send_streaming_message()    │
            │  (Core streaming logic)       │
            └───────────────────────────────┘
```

---

## State Management

### State Transitions

```
┌─────────────────────────────────────────────────────────────┐
│                    USER STATE MACHINE                        │
└─────────────────────────────────────────────────────────────┘

    [INITIAL]
        │
        │ on_start()
        ▼
    [LOGGING_IN]
        │
        │ _login() succeeds
        ▼
    [AUTHENTICATED]
        │
        │ _start_simulation() succeeds
        ▼
    [SIMULATION_READY]
        │
        │ messages_sent == 0
        │ send_begin_message()
        ▼
    [CONVERSATION_STARTED]
        │
        │ messages_sent > 0
        │ send_chat_message() repeatedly
        │
        │ messages_sent < 10
        │ ──────────────────┐
        │                   │
        │ messages_sent >= 10
        │ _start_simulation() (restart)
        │                   │
        └───────────────────┘
                │
                ▼
        [SIMULATION_READY] (loop back)
```

### State Variables Over Time

```
Time →
┌─────────────────────────────────────────────────────────────┐
│ access_token:        [null] → [jwt_token]                    │
│ user_progress_id:    [null] → [123] → [456] (on restart)     │
│ current_scene_id:    [null] → [456] → [789] (on restart)     │
│ simulation_started:  [false] → [true]                         │
│ messages_sent:       [0] → [1] → [2] → ... → [10] → [0]     │
└─────────────────────────────────────────────────────────────┘
```

---

## Streaming Mechanism

### Detailed Flow: _send_streaming_message()

```
┌─────────────────────────────────────────────────────────────┐
│  _send_streaming_message(message, request_name)               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Initialize Metrics                   │
        │  - start_time = time.time()           │
        │  - ttfb = None                        │
        │  - total_response = ""                │
        │  - chunk_count = 0                    │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  POST /api/simulation/linear-chat-stream│
        │  Headers:                              │
        │    Authorization: Bearer {token}       │
        │    Accept: text/event-stream           │
        │  Body:                                 │
        │    simulation_id, user_id, scene_id,   │
        │    message, user_progress_id           │
        │  stream=True  ← KEY: Enable streaming  │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Response Status Check                │
        │  if status != 200: return False       │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  STREAM CONSUMPTION LOOP              │
        │  for chunk in response.iter_lines():  │
        │    ┌───────────────────────────────┐  │
        │    │  if chunk:                   │  │
        │    │    chunk_count++             │  │
        │    │                              │  │
        │    │    if ttfb is None:          │  │
        │    │      ttfb = now - start_time │  │
        │    │      (FIRST BYTE RECEIVED!)  │  │
        │    │                              │  │
        │    │    Decode chunk:             │  │
        │    │    "data: {...}" → JSON      │  │
        │    │                              │  │
        │    │    Extract:                  │  │
        │    │    - content: "token text"   │  │
        │    │    - done: false/true        │  │
        │    │                              │  │
        │    │    total_response += content │  │
        │    │                              │  │
        │    │    if done == true:          │  │
        │    │      break (stream complete) │  │
        │    └───────────────────────────────┘  │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Calculate Total Time                 │
        │  total_time = now - start_time        │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Log Metrics                         │
        │  - TTFB: {ttfb}ms                    │
        │  - Total: {total_time}ms             │
        │  - Chunks: {chunk_count}             │
        │  - Characters: {len(total_response)} │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Fire Custom Event                    │
        │  events.request.fire(                 │
        │    type="STREAM_TTFB",                │
        │    response_time=ttfb                  │
        │  )                                    │
        └───────────────────────────────────────┘
```

### SSE Stream Format

```
Server sends chunks in this format:

data: {"content": "Hello", "done": false, "persona_name": "John", "persona_id": "1"}\n\n
data: {"content": " there", "done": false, "persona_name": "John", "persona_id": "1"}\n\n
data: {"content": "!", "done": true, "persona_name": "John", "persona_id": "1"}\n\n

Each chunk:
- Starts with "data: "
- Contains JSON with:
  - content: The text token
  - done: Whether stream is complete
  - persona_name: Which AI persona responded
  - persona_id: ID of the persona
- Ends with \n\n (double newline)
```

### TTFB Measurement

```
Timeline Visualization:

Request Sent
    │
    │  [Processing Time]
    │  ────────────────────┐
    │                       │
    │                       ▼
    │              First Chunk Arrives
    │              ────────────────────► TTFB measured here!
    │                       │
    │                       │  [Streaming Time]
    │                       │  ────────────────────┐
    │                       │                       │
    │                       │                       ▼
    │                       │              Last Chunk Arrives
    │                       │              ────────────────────► Total time measured
    │                       │                       │
    │                       │                       │
    └───────────────────────┴───────────────────────┘
         Total Response Time
```

---

## Task System

### Task Weights & Probability

```
Locust uses weighted random selection:

send_begin_message:  weight = 1
send_chat_message:   weight = 10
─────────────────────────────────
Total weight:        11

Probability:
- send_begin_message:  1/11  ≈ 9.1%
- send_chat_message:  10/11 ≈ 90.9%

This means:
- Begin message is sent once at start
- Chat messages are sent 10x more frequently
- Matches real user behavior
```

### Task Execution Logic

```
┌─────────────────────────────────────────────────────────────┐
│  send_begin_message()                                        │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Check: Has access_token?             │
        │  ──NO──→ Try _login() → return        │
        │  ──YES─→ Continue                      │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Check: simulation_started?            │
        │  ──NO──→ _start_simulation() → return│
        │  ──YES─→ Continue                      │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Check: messages_sent == 0?           │
        │  ──NO──→ return (already sent)        │
        │  ──YES─→ Send "begin" message          │
        │          messages_sent++               │
        └───────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  send_chat_message()                                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Check: Has token & simulation started?│
        │  ──NO──→ return (skip)                │
        │  ──YES─→ Continue                     │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Check: messages_sent == 0?           │
        │  ──YES─→ Call send_begin_message()    │
        │          return                       │
        │  ──NO──→ Continue                     │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Check: messages_sent >= 10?          │
        │  ──YES─→ _start_simulation() (restart)│
        │          return                        │
        │  ──NO──→ Continue                      │
        └───────────────────────────────────────┘
                            │
                            ▼
        ┌───────────────────────────────────────┐
        │  Pick random message from SAMPLE_MESSAGES│
        │  Send via _send_streaming_message()   │
        │  messages_sent++                       │
        └───────────────────────────────────────┘
```

---

## Event Lifecycle

### Locust Event Hooks

```
┌─────────────────────────────────────────────────────────────┐
│  Test Lifecycle Events                                       │
└─────────────────────────────────────────────────────────────┘

    [Test Start]
        │
        │ @events.test_start.add_listener
        │ on_test_start() called
        │
        │ Logs:
        │ - Target URL
        │ - Region
        │ - Simulation ID
        │ - Test configuration
        │
        ▼
    [Test Running]
        │
        │ Multiple E2EStreamingUser instances:
        │ - on_start() for each user
        │ - Task loop running
        │ - Metrics collected
        │
        ▼
    [Test Stop]
        │
        │ @events.test_stop.add_listener
        │ on_test_stop() called
        │
        │ Logs:
        │ - Total requests
        │ - Failures
        │ - Response times (avg, P95, P99)
        │ - Per-endpoint statistics
        │
        ▼
    [Test Complete]
```

### Custom Events

```
During streaming, custom events are fired:

_send_streaming_message()
    │
    │ After measuring TTFB
    │
    ▼
events.request.fire(
    request_type="STREAM_TTFB",
    name="{request_name} (TTFB)",
    response_time=ttfb,
    ...
)

This allows Locust to track TTFB separately
from total response time in statistics.
```

---

## Key Concepts Explained

### 1. **Why Streaming?**
- Real frontend uses SSE (Server-Sent Events)
- Users see responses appear gradually (token by token)
- TTFB is what users actually perceive
- Must consume full stream to measure realistic load

### 2. **Why Two Time Metrics?**
- **TTFB**: When user sees first response (perceived performance)
- **Total Time**: When entire response completes (server performance)
- Both matter for different reasons

### 3. **Why Task Weights?**
- `send_begin_message`: weight 1 (rare, only at start)
- `send_chat_message`: weight 10 (common, most user actions)
- Locust picks tasks randomly based on weights
- Matches real user behavior distribution

### 4. **Why Session Restart?**
- After 10 messages, restart simulation
- Prevents sessions from getting too long
- Simulates multiple user sessions
- Keeps test data fresh

### 5. **Error Handling**
- Login failures don't crash test
- Stream errors are logged but test continues
- Each user instance is independent
- Locust tracks failures in statistics

---

## Code Flow Summary

```
1. Locust spawns N users (e.g., 10 users)
   │
   ├─→ User 1: on_start() → login → start simulation → task loop
   ├─→ User 2: on_start() → login → start simulation → task loop
   ├─→ User 3: on_start() → login → start simulation → task loop
   └─→ ... (all run concurrently)
   
2. Each user in task loop:
   │
   ├─→ Wait 5-15 seconds (random)
   │
   ├─→ Pick task (9% begin, 91% chat)
   │
   ├─→ Execute task:
   │   ├─→ send_begin_message() OR
   │   └─→ send_chat_message()
   │       │
   │       └─→ _send_streaming_message()
   │           ├─→ POST to /linear-chat-stream
   │           ├─→ Consume stream chunk by chunk
   │           ├─→ Measure TTFB (first chunk)
   │           ├─→ Measure total time (all chunks)
   │           └─→ Log metrics
   │
   └─→ Repeat until test duration ends

3. Test stops:
   │
   └─→ on_test_stop() → Print statistics
```

---

## Example Execution Trace

```
[User 1] Starting with email loadtest_user_5@test.com
[User 1] ✓ Logged in
[User 1] ✓ Started simulation | progress_id=123, scene_id=456
[User 1] → Sending 'begin' message...
[User 1] Chat Begin (Stream) | TTFB=450ms ✓ | Total=3200ms | Chunks=45 | Chars=1200
[User 1] → Sending message #1: 'Hello! Can you tell me more...'
[User 1] Chat Message (Stream) | TTFB=520ms ✓ | Total=2800ms | Chunks=38 | Chars=950
[User 1] → Sending message #2: 'What are the main challenges...'
[User 1] Chat Message (Stream) | TTFB=480ms ✓ | Total=3100ms | Chunks=42 | Chars=1100
...
[User 1] ↻ Session complete - restarting
[User 1] ✓ Started simulation | progress_id=789, scene_id=101
[User 1] → Sending 'begin' message...
...
```

---

## Configuration Dependencies

The test relies on `config.py` for:

- **base_url**: Target server (e.g., "https://backend-europe.up.railway.app")
- **simulation_id**: Which simulation to test
- **test_user_count**: How many test users exist (1-100)
- **test_user_prefix**: "loadtest_user_"
- **test_user_domain**: "@test.com"
- **test_password**: Password for all test users
- **min_wait / max_wait**: Time between requests (5-15 seconds)

All loaded from `loadtest.env` file.

---

## Summary

This test is a **realistic load test** that:
1. ✅ Simulates actual user behavior (login → start → chat)
2. ✅ Uses real streaming endpoint (SSE)
3. ✅ Measures user-perceived metrics (TTFB)
4. ✅ Consumes full streams (realistic load)
5. ✅ Handles errors gracefully
6. ✅ Provides detailed statistics

It's designed to find performance bottlenecks that affect **real users**, not just server metrics.



