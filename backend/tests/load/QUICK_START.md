# Load Testing - Quick Start Guide

## 🚀 Get Running in 5 Minutes

### Step 1: Install Locust
```bash
pip install locust
# or
pip install -r tests/load/requirements-load-test.txt
```

### Step 2: Start Backend
```bash
# Terminal 1
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Step 3: Run a Test

**Option A: Quick Smoke Test (1 minute)**
```bash
# Terminal 2
cd backend
./tests/load/run_smoke_test.sh
```

**Option B: Demo Rehearsal (10 minutes)**
```bash
./tests/load/run_demo_test.sh
```

**Option C: Interactive Web UI**
```bash
locust -f tests/load/locustfile.py --host http://localhost:8000
# Open http://localhost:8089
# Enter: 60 users, spawn rate 10
# Click "Start swarming"
```

---

## 📊 What You'll See

### Command Line Output
```
[2024-12-07 10:30:15] Ramping to 60 users at 10 spawns/s...
[2024-12-07 10:30:21] All 60 users spawned

Type     Name                              # reqs  # fails  Avg    Min    Max    Med
------------------------------------------------------------------------
POST     Register Student                      60      0   450    320    890    420
POST     Login                                 60      0   320    180    650    310
GET      View Dashboard (Auth Check)          600      2   180    45     1200   150
GET      Get Notifications                    300      0   220    120    450    210
------------------------------------------------------------------------
         Aggregated                          1020      2   237    45     1200   180

🏁 LOAD TEST COMPLETED
Total Requests: 1020
Failures: 2
Success Rate: 99.80%
Average Response Time: 237.50ms
```

### Web UI (http://localhost:8089)
- Real-time graphs
- Request statistics
- Failure tracking
- Download reports

---

## ✅ Success Criteria

**For Demo (60 users):**
- ✅ Success rate: >95%
- ✅ Average response: <500ms
- ✅ Max response: <2s
- ✅ No crashes

**For Stress Test (200 users):**
- ✅ Success rate: >90%
- ✅ Average response: <1s
- ✅ System recovers gracefully
- ✅ Pool warnings are ok

---

## 🔍 Monitor During Tests

### Watch Backend Logs
```bash
# Terminal 3
tail -f backend.log | grep -E "Pool|WARNING|ERROR"
```

**Look for:**
- ✅ `Database connection pool: New connection established`
- ⚠️ `Database connection pool usage HIGH: 125/150` (expected under load)
- 🔴 `Connection pool timeout` (BAD - pool exhausted)

### Watch Database
```bash
# Terminal 4
watch -n 1 "psql -c 'SELECT count(*) FROM pg_stat_activity WHERE state = \"active\";'"
```

**Should stay below 150 connections**

---

## 🎯 Pre-Demo Checklist

**1 week before:**
```bash
./tests/load/run_demo_test.sh
```
✅ Success rate >95%? Ready to go!

**1 day before:**
```bash
./tests/load/run_smoke_test.sh
```
✅ Quick verification everything works

**30 minutes before demo:**
```bash
python pre_demo_health_check.py
./tests/load/run_smoke_test.sh
```
✅ Final check

---

## 🆘 Troubleshooting

### Test Won't Start
```
Error: Connection refused
```
→ Backend not running? Check `http://localhost:8000/docs`

### High Failures
```
Failures: 500/1000 (50%)
```
→ Check backend logs for errors
→ Verify PostgreSQL max_connections ≥ 200

### Slow Responses
```
Average Response Time: 3500ms
```
→ Connection pool full? Check logs for "HIGH" warnings
→ Database slow? Check query performance

---

## 📁 Test Scripts

| Script | Users | Duration | Purpose |
|--------|-------|----------|---------|
| `run_smoke_test.sh` | 10 | 1 min | Quick health check |
| `run_demo_test.sh` | 60 | 10 min | Demo rehearsal |
| `run_stress_test.sh` | 200 | 5 min | Find limits |

---

## 📖 Full Documentation

See `README.md` for:
- Detailed test scenarios
- Result interpretation
- Advanced usage
- FAQ

---

**Questions? Issues? Check the logs first!** 🔍
