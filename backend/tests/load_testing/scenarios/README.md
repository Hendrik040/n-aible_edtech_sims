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

### 1. Registration Load Test (`registration_load_test.py`)

Tests mass user registration capability.

**User Classes:**
- `RegistrationLoadTestUser` - Register only, then idle
- `RegistrationAndChatUser` - Register, then chat

**What it tests:**
- `/api/auth/users/register` endpoint
- `/api/auth/users/login` endpoint
- Database write performance
- Password hashing throughput (bcrypt)

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

### 2. Chat Load Test (`chat_load_test.py`)

Tests chat simulation under load with existing users.

**User Classes:**
- `ChatLoadTestUser` - Login with existing user, then chat

**What it tests:**
- `/api/simulation/chat` endpoint
- AI API throughput
- WebSocket or polling performance
- Database read/write for chat history

**Prerequisites:**
- Pre-created test users in database
- Published simulation accessible to test users

**Example:**
```bash
python -m locust -f scenarios/chat_load_test.py \
  --headless \
  -u 50 \
  -r 2 \
  -t 10m \
  ChatLoadTestUser
```

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

