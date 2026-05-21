# Load Testing Scenarios

This directory contains Locust-based load testing scenarios for the n-aible EdTech platform.

---

## 📋 Table of Contents

1. [Quick Start](#-quick-start)
2. [Prerequisites](#-prerequisites)
3. [Configuration](#-configuration)
4. [Available Scenarios](#-available-scenarios)
5. [Running Tests](#-running-tests)
6. [Understanding Results](#-understanding-results)
7. [Troubleshooting](#-troubleshooting)

---

## 🚀 Quick Start

```bash
# 1. Navigate to the load_testing directory
cd backend/tests/load_testing

# 2. Activate your virtual environment
source ../../.venv/bin/activate  # or your venv path

# 3. Install Locust if not already installed
pip install locust

# 4. Configure your environment (edit loadtest.env)
cp loadtest.env.example loadtest.env
# Edit loadtest.env with your settings

# 5. Run a quick test (10 users, 60 seconds)
python -m locust -f scenarios/registration_load_test.py \
  --headless \
  -u 10 \
  -r 2 \
  -t 60s \
  RegistrationLoadTestUser
```

---

## ✅ Prerequisites

### 1. Python Dependencies

```bash
pip install locust python-dotenv
```

### 2. Environment Configuration

Create `loadtest.env` in the `load_testing` directory:

```bash
cp loadtest.env.example loadtest.env
```

### 3. Target Server

Ensure your target server is running and accessible:
- **Local**: `http://localhost:8000`
- **Staging**: Your Railway staging URL
- ⚠️ **NEVER run load tests against production!**

---

## ⚙️ Configuration

### Environment Variables (`loadtest.env`)

| Variable | Description | Example |
|----------|-------------|---------|
| `LOAD_TEST_URL` | Target backend URL | `https://backend-staging.up.railway.app` |
| `LOAD_TEST_ENVIRONMENT` | Environment name | `staging` |
| `TEST_USER_PREFIX` | Email prefix for generated users | `loadtest_user_` |
| `TEST_USER_DOMAIN` | Email domain (NO underscore!) | `@testload.com` |
| `TEST_USER_PASSWORD` | Password for test users | `testpassword123` |
| `DEFAULT_USERS` | Default concurrent users | `100` |
| `DEFAULT_SPAWN_RATE` | Users spawned per second | `2` |
| `DEFAULT_RUN_TIME` | Default test duration | `15m` |
| `DEBUG_MODE` | Enable verbose logging | `true` |


## 📦 Available Scenarios

### ⭐ RECOMMENDED TEST FLOW

<<<<<<< HEAD
**The registration and chat tests are designed to work together:**
=======
**The registration and streaming tests are designed to work together:**
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  STEP 1: Registration Test (creates users 1-100)                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Registers users with PREDICTABLE emails:                                │
│    loadtest_user_opt1@testnew.com                                       │
│    loadtest_user_opt2@testnew.com                                       │
│    ...                                                                   │
│    loadtest_user_opt100@testnew.com                                     │
│                                                                          │
│  All users get the SAME password from TEST_USER_PASSWORD                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
<<<<<<< HEAD
│  STEP 2: Chat Test (logs in as users 1-100)                              │
=======
│  STEP 2: E2E Streaming Test (logs in as users 1-100)                    │
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Logs in with the SAME predictable emails:                               │
│    loadtest_user_opt1@testnew.com + TEST_USER_PASSWORD                  │
│    loadtest_user_opt2@testnew.com + TEST_USER_PASSWORD                  │
│    ...                                                                   │
│                                                                          │
│  ✓ Credentials MATCH because both use config.get_test_user_email()      │
<<<<<<< HEAD
=======
│  ✓ Uses REAL streaming endpoint (/linear-chat-stream)                   │
│  ✓ Measures TTFB (user-perceived performance)                          │
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**Quick Commands:**

```bash
# STEP 1: Create 100 test users (run once, or whenever you need fresh users)
python -m locust -f scenarios/registration_load_test.py \
  --headless -u 100 -r 5 -t 3m RegistrationLoadTestUser

<<<<<<< HEAD
# STEP 2: Run chat load test with those users
=======
# STEP 2: Run E2E streaming test (most realistic - recommended)
python -m locust -f scenarios/e2e_streaming_test.py \
  --headless -u 100 -r 10 -t 10m E2EStreamingUser

# STEP 2 (Alternative): Run non-streaming chat test for comparison
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)
python -m locust -f scenarios/chat_load_test.py \
  --headless -u 100 -r 10 -t 10m ChatLoadTestUser
```

> 💡 **Note:** If you run registration multiple times, existing users will be skipped (logged in instead). This is by design!

---

<<<<<<< HEAD
### 1. Registration Load Test (`registration_load_test.py`)
=======
### 1. E2E Streaming Test (`e2e_streaming_test.py`) ⭐ **NEW - RECOMMENDED**

**Most realistic test** - Replicates the actual frontend user experience with Server-Sent Events (SSE) streaming.

**User Classes:**
- `E2EStreamingUser` - Login, start simulation, send streaming chat messages

**What it tests:**
- `/api/simulation/start` - Start simulation endpoint
- `/api/simulation/linear-chat-stream` - **Streaming** chat endpoint (SSE)
- **TTFB (Time To First Byte)** - User-perceived performance
- **Total response time** - Complete stream consumption
- AI streaming throughput (OpenAI streaming)
- Realistic load (consumes full stream, not just fires requests)

**Key Differences from `chat_load_test.py`:**
- ✅ Uses `/linear-chat-stream` (SSE) - same as real frontend
- ✅ Measures TTFB - when user sees first response
- ✅ Consumes entire stream - realistic server load
- ✅ Cookie-based authentication (matches frontend)

**Test Flow per User:**
1. Login with test credentials (cookie auth)
2. POST `/api/simulation/start` (get `user_progress_id`)
3. Send "begin" message via streaming endpoint
4. Send ~10 chat messages via streaming endpoint
5. Measure TTFB and total time for each message
6. Restart simulation after 10 messages (simulate new session)

**Prerequisites:**
1. **Run Registration Test First!**
   ```bash
   python -m locust -f scenarios/registration_load_test.py \
     --headless -u 100 -r 5 -t 3m RegistrationLoadTestUser
   ```

2. **Configure a published simulation** in `loadtest.env`:
   ```bash
   TEST_SIMULATION_ID=1  # Must be a valid, published simulation ID
   ```

3. **Test users must have access to the simulation**

**Example - Quick Test (10 users):**
```bash
python -m locust -f scenarios/e2e_streaming_test.py \
  --headless \
  -u 10 \
  -r 2 \
  -t 2m \
  E2EStreamingUser
```

**Example - Full Test (100 users):**
```bash
python -m locust -f scenarios/e2e_streaming_test.py \
  --headless \
  -u 100 \
  -r 10 \
  -t 10m \
  --html reports/e2e_streaming_$(date +%Y%m%d_%H%M%S).html \
  E2EStreamingUser
```

**Expected Metrics:**
- TTFB: < 1000ms (good), < 3000ms (acceptable), > 3000ms (poor)
- Total Time: ~3-10 seconds (depends on response length)
- Stream Chunks: 30-50 chunks per response (typical)

**Documentation:**
- See `E2E_STREAMING_TEST_VISUAL_MAP.md` for detailed visual explanation of how the test works

---

### 2. Registration Load Test (`registration_load_test.py`)
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)

Tests mass user registration capability.

**User Classes:**
- `RegistrationLoadTestUser` - Register only, then idle
- `RegistrationAndChatUser` - Register, then chat

**What it tests:**
- `/api/auth/users/register` endpoint
- `/api/auth/users/login` endpoint
- Database write performance
- Password hashing throughput (bcrypt)

**User Credential Pattern:**
- Email: `{TEST_USER_PREFIX}{N}{TEST_USER_DOMAIN}` (e.g., `loadtest_user_opt1@testnew.com`)
- Password: `{TEST_USER_PASSWORD}` (same for all users)
- N = 1, 2, 3, ... up to `-u` value

**Example:**
```bash
python -m locust -f scenarios/registration_load_test.py \
  --headless \
  -u 100 \
  -r 5 \
  -t 5m \
  RegistrationLoadTestUser
```

---

<<<<<<< HEAD
### 2. Chat Load Test (`chat_load_test.py`)

Tests AI chat simulation under load with 100 concurrent users.
=======
### 3. Chat Load Test (`chat_load_test.py`)

Tests AI chat simulation under load using the **non-streaming** endpoint (for comparison with streaming test).
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)

**User Classes:**
- `ChatLoadTestUser` - Login, start simulation, send chat messages

**What it tests:**
- `/api/simulation/start` - Start simulation endpoint
<<<<<<< HEAD
- `/api/simulation/linear-chat` - Chat message processing
=======
- `/api/simulation/linear-chat` - **Non-streaming** chat endpoint
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)
- AI API throughput (OpenAI)
- Simulation queue performance
- Database read/write for conversations

<<<<<<< HEAD
=======
**Note:** This uses the non-streaming endpoint. For realistic frontend simulation, use `e2e_streaming_test.py` instead.

>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)
**Test Flow per User:**
1. Login with test credentials
2. POST `/api/simulation/start` (get `user_progress_id`)
3. Send "begin" message to initialize simulation
4. Send ~10 chat messages with realistic timing (5-15s between messages)
5. Repeat

**Prerequisites:**
1. **Run Registration Test First!**
   ```bash
   python -m locust -f scenarios/registration_load_test.py \
     --headless -u 100 -r 5 -t 3m RegistrationLoadTestUser
   ```
   This creates users `loadtest_user_opt1@testnew.com` through `loadtest_user_opt100@testnew.com`

2. **Configure a published simulation** in `loadtest.env`:
   ```bash
   TEST_SIMULATION_ID=1  # Must be a valid, published simulation ID
   ```

3. **Test users must have access to the simulation**
   - Either make the simulation public, or
   - Add test users to a cohort with access

**Example - Quick Test (10 users):**
```bash
DEBUG_MODE=true python -m locust -f scenarios/chat_load_test.py \
  --headless \
  -u 10 \
  -r 2 \
  -t 2m \
  ChatLoadTestUser
```

**Example - Full Test (100 users):**
```bash
python -m locust -f scenarios/chat_load_test.py \
  --headless \
  -u 100 \
  -r 10 \
  -t 10m \
  --html reports/chat_$(date +%Y%m%d_%H%M%S).html \
  ChatLoadTestUser
```

**Expected Response Times:**
- Start Simulation: ~1-2 seconds (database + initial setup)
- Begin Message: ~3-5 seconds (AI generates intro)
- Chat Messages: ~3-10 seconds (AI response generation)

---

## 🏃 Running Tests

### Headless Mode (Recommended for CI/CD)

```bash
# Basic format
python -m locust -f scenarios/<SCENARIO>.py \
  --headless \
  -u <USERS> \
  -r <SPAWN_RATE> \
  -t <DURATION> \
  <USER_CLASS>
```

### CLI Arguments

| Argument | Description | Example |
|----------|-------------|---------|
| `-f` | Scenario file | `scenarios/registration_load_test.py` |
| `-u` | Number of concurrent users | `100` |
| `-r` | Spawn rate (users/second) | `5` |
| `-t` | Test duration | `60s`, `5m`, `1h` |
| `--headless` | Run without web UI | (flag) |
| `--only-summary` | Show only final summary | (flag) |
| `--html` | Generate HTML report | `report.html` |
| `--csv` | Generate CSV reports | `results` |

### Examples

#### Quick Smoke Test (10 users, 30 seconds)
```bash
DEBUG_MODE=true python -m locust -f scenarios/registration_load_test.py \
  --headless \
  -u 10 \
  -r 2 \
  -t 30s \
  RegistrationLoadTestUser
```

#### Full Load Test (100 users, 15 minutes)
```bash
python -m locust -f scenarios/registration_load_test.py \
  --headless \
  -u 100 \
  -r 5 \
  -t 15m \
  --html reports/registration_$(date +%Y%m%d_%H%M%S).html \
  RegistrationLoadTestUser
```

#### With Live Stats (no --only-summary)
```bash
python -m locust -f scenarios/registration_load_test.py \
  --headless \
  -u 10 \
  -r 2 \
  -t 60s \
  RegistrationLoadTestUser
```

### Web UI Mode

For interactive testing with a dashboard:

```bash
python -m locust -f scenarios/registration_load_test.py
# Open http://localhost:8089 in browser
```

---

## 📊 Understanding Results

### Key Metrics

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| **Avg Response Time** | < 500ms | 500-2000ms | > 2000ms |
| **P95 Response Time** | < 1000ms | 1-5s | > 5s |
| **Failure Rate** | < 1% | 1-5% | > 5% |
| **Requests/sec** | > 10 | 5-10 | < 5 |

### Sample Output

```
Type     Name                              # reqs    # fails |   Avg    Min    Max   Med |  req/s  failures/s
--------|--------------------------------|--------|---------|--------|-------|-------|------|--------|----------
POST     [Auth] Register                     100   0(0.00%) |    450    200    890   420 |   5.50        0.00
POST     [Auth] Login (post-register)        100   0(0.00%) |    180     80    350   150 |   5.50        0.00
--------|--------------------------------|--------|---------|--------|-------|-------|------|--------|----------
         Aggregated                          200   0(0.00%) |    315     80    890   250 |  11.00        0.00
```

### Reading the Numbers

- **# reqs**: Total requests made
- **# fails**: Failed requests (with percentage)
- **Avg**: Average response time in milliseconds
- **Min/Max**: Fastest and slowest response times
- **Med**: Median (50th percentile) response time
- **req/s**: Requests per second throughput
- **failures/s**: Failure rate per second

---

## 🔧 Troubleshooting

### Common Issues

#### 1. "Host not set" Error
```
locust.exception.LocustError: You must specify the base host.
```
**Fix:** Ensure `LOAD_TEST_URL` is set in `loadtest.env`

#### 2. 500 Errors on Registration
```
ResponseValidationError: invalid email address
```
**Fix:** Remove underscores from `TEST_USER_DOMAIN`:
```bash
# Change from
TEST_USER_DOMAIN=@test_opti.com
# To
TEST_USER_DOMAIN=@testopti.com
```

#### 3. 0 Requests Completed
Requests are taking too long (> test duration).

**Causes:**
- Synchronous bcrypt blocking the event loop
- Database connection pool exhaustion
- Neon cold start delays
- Single worker processing sequentially

**Debug:** Run with `DEBUG_MODE=true` and check backend logs.

#### 4. TypeError on Shutdown
```
TypeError: '<' not supported between instances of 'NoneType' and 'str'
```
This is a known Locust bug. It doesn't affect test results - just ignore it.

#### 5. Login Fails After Registration
Check backend logs for the actual error. Common causes:
- Password hashing timing out
- Database connection issues
- Incorrect endpoint paths

### Debug Mode

Enable verbose logging:

```bash
DEBUG_MODE=true python -m locust -f scenarios/registration_load_test.py ...
```

This adds timestamps and detailed request/response logging.

---

## 📁 Directory Structure

```
load_testing/
├── scenarios/
<<<<<<< HEAD
│   ├── README.md                 # This file
│   ├── registration_load_test.py # Registration scenarios
│   ├── chat_load_test.py         # Chat scenarios
│   └── __init__.py
├── user_behaviors/
│   ├── base.py                   # Base user class with auth
│   ├── registration_user.py      # Registration behavior
│   └── chat_user.py              # Chat behavior
├── config.py                     # Configuration loader
├── loadtest.env                  # Your local config (gitignored)
├── loadtest.env.example          # Example config
└── reports/                      # Generated reports
=======
│   ├── README.md                      # This file
│   ├── e2e_streaming_test.py         # ⭐ E2E streaming test (most realistic)
│   ├── E2E_STREAMING_TEST_VISUAL_MAP.md  # Visual guide for E2E test
│   ├── registration_load_test.py      # Registration scenarios
│   ├── chat_load_test.py              # Chat scenarios (non-streaming)
│   └── __init__.py
├── user_behaviors/
│   ├── base.py                        # Base user class with auth
│   ├── registration_user.py           # Registration behavior
│   └── chat_user.py                   # Chat behavior
├── config.py                          # Configuration loader
├── loadtest.env                       # Your local config (gitignored)
├── loadtest.env.example               # Example config
└── reports/                           # Generated reports
>>>>>>> f704b47 (feat(load-testing): support old codebase comparison with US-STAG region)
```

---

## 🎯 Best Practices

1. **Start small**: Test with 10 users before scaling to 100
2. **Watch the backend logs**: Monitor Railway/server logs during tests
3. **Check database metrics**: Watch Neon connection usage
4. **Ramp up gradually**: Use spawn rate of 2-5 users/second
5. **Run multiple times**: Results can vary - run 3+ tests
6. **Never test production**: Use staging/dev environments only
7. **Clean up test data**: Delete test users after testing

---

## 📚 Additional Resources

- [Locust Documentation](https://docs.locust.io/)
- [Railway Performance Guide](https://docs.railway.com/guides/optimize-performance)
- [Neon Connection Pooling](https://neon.tech/docs/connect/connection-pooling)

