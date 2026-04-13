# Load Testing Framework

Performance and load testing tools for the n-aible EdTech platform.

---

## 🚀 Quick Start

```bash
# 1. Navigate here
cd backend/tests/load_testing

# 2. Setup environment
cp loadtest.env.example loadtest.env
# Edit loadtest.env - set TARGET_REGION

# 3. Activate virtual environment
source venv/bin/activate

# 4. Run a quick test
locust -f scenarios/chat_load_test.py --headless -u 10 -r 2 -t 1m
```

---

## 📦 Available Tools

### 1. E2E Streaming Test ⭐ **NEW**
**Most realistic test** - Replicates actual frontend user experience with Server-Sent Events (SSE) streaming.

**Key Features:**
- Uses `/api/simulation/linear-chat-stream` (same as real frontend)
- Measures **TTFB** (Time To First Byte) - what users actually perceive
- Measures total response time
- Consumes full stream (realistic load)

```bash
locust -f scenarios/e2e_streaming_test.py --headless -u 10 -r 2 -t 2m
```

**Documentation:** See `scenarios/E2E_STREAMING_TEST_VISUAL_MAP.md` for detailed visual explanation.

### 2. Chat Load Test
Test AI chat simulation under concurrent user load (non-streaming endpoint).

```bash
locust -f scenarios/chat_load_test.py --headless -u 50 -r 5 -t 5m
```

### 3. Registration Load Test
Test mass user registration.

```bash
locust -f scenarios/registration_load_test.py --headless -u 100 -r 5 -t 3m
```

### 4. Multi-Region Benchmark ⭐
Compare performance across EU, US-DEV, and US-EXP regions with automatic dashboard generation.

```bash
# Test all regions (30 users, 2 minutes each)
python multi_region_benchmark.py

# Custom settings
python multi_region_benchmark.py --regions EU US-DEV --users 50 --duration 3m

# Quick smoke test
python multi_region_benchmark.py --users 10 --duration 1m
```

**Output:**
- 📊 Interactive HTML dashboard with charts
- 📁 JSON results for analysis
- 🏆 Console summary with winner

---

## ⚙️ Configuration

### Region Selection

Edit `loadtest.env`:

```env
# Primary setting - just set the region!
TARGET_REGION=US-DEV

# Available regions:
# EU      -> https://backend-europe.up.railway.app
# US-DEV  -> https://backend-development-0519.up.railway.app
# US-EXP  -> https://backend-experimental-246c.up.railway.app
```

### Test Users

```env
TEST_USER_PREFIX=loadtest_user_
TEST_USER_DOMAIN=@test.com
TEST_USER_PASSWORD=testpassword123
TEST_SIMULATION_ID=96
```

---

## 📁 Structure

```
load_testing/
├── config.py                    # Configuration & region mapping
├── loadtest.env                 # Your local settings (gitignored)
├── loadtest.env.example         # Example configuration
├── multi_region_benchmark.py    # Multi-region comparison tool
├── locustfile.py                # Main Locust entry point
├── scenarios/
│   ├── README.md                # Detailed scenario documentation
│   ├── e2e_streaming_test.py    # ⭐ E2E streaming test (most realistic)
│   ├── E2E_STREAMING_TEST_VISUAL_MAP.md  # Visual guide for E2E test
│   ├── chat_load_test.py        # Chat simulation test (non-streaming)
│   └── registration_load_test.py
├── user_behaviors/
│   ├── base.py                  # Base authenticated user
│   ├── chat_user.py             # Chat behavior
│   └── registration_user.py     # Registration behavior
└── reports/                     # Generated reports (gitignored)
```

---

## 📚 Documentation

For detailed documentation on each scenario, see:
- **[Scenarios README](scenarios/README.md)** - Full test documentation, troubleshooting, examples

---

## 🎯 Recommended Test Flow

1. **Create test users** (once):
   ```bash
   locust -f scenarios/registration_load_test.py --headless -u 100 -r 5 -t 3m
   ```

2. **Run E2E streaming test** (most realistic - recommended):
   ```bash
   locust -f scenarios/e2e_streaming_test.py --headless -u 100 -r 10 -t 10m
   ```
   This test uses the actual streaming endpoint and measures TTFB.

3. **Run chat tests** (non-streaming endpoint - for comparison):
   ```bash
   locust -f scenarios/chat_load_test.py --headless -u 100 -r 10 -t 10m
   ```

4. **Compare regions** (optional):
   ```bash
   python multi_region_benchmark.py
   ```

