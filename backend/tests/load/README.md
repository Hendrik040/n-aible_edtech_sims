# Load Testing with Locust

Professional load testing setup for the n-aible platform using Locust.

## Quick Start

### 1. Install Locust

```bash
pip install locust
# or
pip install -r requirements-load-test.txt
```

### 2. Start Your Backend

```bash
# Make sure backend is running
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Run Load Tests

#### Option A: Interactive Web UI (Recommended for First Time)
```bash
cd backend
locust -f tests/load/locustfile.py --host http://localhost:8000

# Open browser to http://localhost:8089
# Enter number of users and spawn rate
# Click "Start swarming"
```

#### Option B: Headless (Command Line)
```bash
# Demo scenario: 60 concurrent users
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 60 \
  --spawn-rate 10 \
  --run-time 5m \
  --headless

# Registration stress test: 200 concurrent users
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 200 \
  --spawn-rate 20 \
  --run-time 3m \
  --headless

# Quick smoke test: 10 users
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 10 \
  --spawn-rate 5 \
  --run-time 1m \
  --headless
```

---

## Test Scenarios

### Scenario 1: Demo Rehearsal (60 Users)
**Purpose:** Simulate your actual demo with 50-60 users.

```bash
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 60 \
  --spawn-rate 12 \
  --run-time 10m \
  --headless \
  --html reports/demo_rehearsal_$(date +%Y%m%d_%H%M%S).html
```

**What it tests:**
- Burst registration (all 60 users register at once)
- Concurrent logins
- Dashboard loads
- Notification checks
- Realistic user behavior patterns

**Expected results:**
- Success rate: >95%
- Average response time: <500ms
- Max response time: <2s
- Peak connections: ~120-150

### Scenario 2: Registration Stress Test (200 Users)
**Purpose:** Test connection pool at maximum capacity.

```bash
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 200 \
  --spawn-rate 20 \
  --run-time 5m \
  --headless \
  --html reports/registration_stress_$(date +%Y%m%d_%H%M%S).html
```

**What it tests:**
- Maximum connection pool usage (150 connections)
- Queue handling when pool is full
- Timeout behavior
- Recovery after burst

**Expected results:**
- Success rate: >90%
- Some requests may timeout (expected at this scale)
- Pool warnings in logs
- System should recover gracefully

### Scenario 3: Sustained Load (30 Users, 30 Minutes)
**Purpose:** Test for memory leaks, connection pool recycling.

```bash
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 30 \
  --spawn-rate 5 \
  --run-time 30m \
  --headless \
  --html reports/sustained_load_$(date +%Y%m%d_%H%M%S).html
```

**What it tests:**
- Connection pool recycling (pool_recycle=300s)
- Memory stability over time
- No connection leaks
- Consistent performance

---

## Understanding the Results

### Web UI (http://localhost:8089)

**Key Metrics:**
- **Total Requests:** How many API calls were made
- **Failures:** HTTP errors, timeouts
- **RPS (Requests/sec):** Throughput
- **Response Times:** p50, p95, p99 percentiles

**Charts:**
- **Total Requests per Second:** Should be steady, not spiking
- **Response Times:** Should stay low and consistent
- **Number of Users:** Shows ramp-up pattern

### Command Line Output

```
[2024-12-07 10:30:15] INFO: Ramping to 60 users...
[2024-12-07 10:30:25] INFO: All 60 users spawned

Statistics:
┌─────────────────────────────────────────────────────────┐
│ Name                          │ # reqs │ # fails │ Avg │
├───────────────────────────────┼────────┼─────────┼─────┤
│ Register Student              │    60  │    0    │ 450 │
│ Login                         │    60  │    0    │ 320 │
│ View Dashboard (Auth Check)   │   600  │    2    │ 180 │
│ Get Notifications             │   300  │    0    │ 220 │
└─────────────────────────────────────────────────────────┘

🏁 LOAD TEST COMPLETED
Total Requests: 1020
Failures: 2
Success Rate: 99.80%
Average Response Time: 237.50ms
```

### What to Watch For

**🟢 Good Signs:**
- Success rate >95%
- Average response time <500ms
- Steady RPS (not dropping over time)
- No "connection pool usage HIGH" warnings in logs

**🟡 Warning Signs:**
- Success rate 90-95%
- Average response time 500-1000ms
- Occasional "pool usage HIGH" warnings
- Some timeouts under heavy load

**🔴 Bad Signs:**
- Success rate <90%
- Average response time >1000ms
- Frequent connection pool exhaustion
- Many timeouts or 500 errors

---

## Monitoring During Tests

### Terminal 1: Run Load Test
```bash
locust -f tests/load/locustfile.py --host http://localhost:8000
```

### Terminal 2: Watch Backend Logs
```bash
# Watch for connection pool warnings
tail -f backend.log | grep -E "Pool|connection|WARNING|ERROR"

# Look for:
# ✅ "Database connection pool: New connection established"
# ⚠️  "Database connection pool usage HIGH: 125/150"
# 🔴 "Connection pool timeout"
```

### Terminal 3: Monitor Database
```bash
# Watch active connections in PostgreSQL
watch -n 1 "psql -c \"SELECT count(*) as active FROM pg_stat_activity WHERE state = 'active';\""

# Should stay below 150 (your pool capacity)
```

---

## Troubleshooting

### Test Fails to Start
```
Error: Connection refused
```
**Fix:** Make sure backend is running on http://localhost:8000

### High Failure Rate
```
Failures: 500/1000 (50%)
```
**Check:**
1. Backend logs for errors
2. PostgreSQL max_connections
3. Connection pool exhaustion warnings

### Slow Response Times
```
Average Response Time: 3500ms
```
**Possible causes:**
1. Database queries are slow
2. Connection pool is full (requests waiting)
3. CPU/memory bottleneck

### Connection Pool Warnings
```
⚠️ Database connection pool usage HIGH: 140/150
```
**This is expected!** It means:
- Your pool is handling the load
- You're using 93% of capacity
- Still have 10 connections buffer

---

## Pre-Demo Checklist

**1 Week Before Demo:**
- [ ] Run Demo Rehearsal test (60 users)
- [ ] Verify success rate >95%
- [ ] Check average response time <500ms
- [ ] Review database logs for issues

**3 Days Before Demo:**
- [ ] Run Registration Stress Test (200 users)
- [ ] Verify pool handles burst load
- [ ] Test recovery after overload

**1 Day Before Demo:**
- [ ] Run Sustained Load test (30 users, 30 min)
- [ ] Check for memory leaks
- [ ] Verify connection recycling works

**Demo Day:**
- [ ] Run Quick Smoke Test (10 users, 1 min)
- [ ] Verify all endpoints working
- [ ] Check database health

---

## Advanced Usage

### Generate HTML Report
```bash
locust -f tests/load/locustfile.py \
  --host http://localhost:8000 \
  --users 60 \
  --spawn-rate 10 \
  --run-time 5m \
  --headless \
  --html reports/load_test_report.html \
  --csv reports/load_test_data
```

### Custom User Mix (80% Students, 20% Professors)
```bash
# Edit locustfile.py and add:
# class CustomLoadTest(StudentUser):
#     weight = 4  # 80%
#
# class CustomProfessor(ProfessorUser):
#     weight = 1  # 20%
```

### Distributed Load Testing (Multiple Machines)
```bash
# Master
locust -f tests/load/locustfile.py --master

# Workers (on other machines)
locust -f tests/load/locustfile.py --worker --master-host=<master-ip>
```

---

## FAQ

**Q: How many users should I test with?**
A: Start with your expected demo size (60), then test 2-3x that (150-200) to find limits.

**Q: How long should tests run?**
A: 5-10 minutes for demo rehearsal, 30+ minutes for sustained load testing.

**Q: What success rate is acceptable?**
A:
- >98% = Excellent
- 95-98% = Good
- 90-95% = Acceptable (investigate failures)
- <90% = Issues need fixing

**Q: Can I test against production?**
A: **NO!** Always test against staging/dev. Load tests can disrupt real users.

**Q: How do I test PDF uploads?**
A: Add a task in ProfessorUser that uploads a small test PDF (be careful - this is heavy!).

---

## Next Steps

After successful load testing:
1. Review HTML reports
2. Identify slow endpoints
3. Optimize database queries if needed
4. Adjust connection pool if necessary
5. Run tests again to verify improvements

**Questions?** Check Locust docs: https://docs.locust.io/
