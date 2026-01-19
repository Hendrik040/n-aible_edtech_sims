# Load Testing Plan: 100 Concurrent Users

## Overview

This document outlines a comprehensive load testing strategy to validate that the n-aible platform can handle **100 concurrent users** using the simulation chat experience simultaneously.

### Goals
1. Verify system stability under load
2. Identify bottlenecks before they affect real users
3. Validate the queue system and routing logic
4. Measure response times and error rates
5. Test the worker-specific Redis key implementation

### Architecture Context (from previous analysis)
- **3 Railway replicas** with worker-specific Redis keys
- **Neon PostgreSQL** with PgBouncer (10,000 pooled connections)
- **Railway Redis** (20 connections per replica = 60 total)
- **OpenAI Tier 4** (~10,000 RPM)
- **Concurrency limits**: 35 streams/replica, 20 AI calls/replica

---

## Prerequisites

### 1. Environment Setup

```bash
# Clone and setup (if not already done)
cd n-aible_edtech_sims

# Create virtual environment for load testing
python -m venv venv-loadtest
source venv-loadtest/bin/activate  # or `venv-loadtest\Scripts\activate` on Windows

# Install load testing tools
pip install locust httpx python-dotenv
```

### 2. Test User Accounts

Create test users in your database (or use existing):
```sql
-- Run via Neon SQL Editor or psql
-- Create 100 test users (adjust as needed)
INSERT INTO users (email, full_name, hashed_password, is_verified, created_at)
SELECT 
    'loadtest_user_' || generate_series || '@test.com',
    'Load Test User ' || generate_series,
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4hJQKYUFocFZOAGe', -- password: "testpassword123"
    true,
    NOW()
FROM generate_series(1, 100);
```

### 3. Test Simulation Data

Ensure you have a published simulation with:
- At least one cohort with test users enrolled
- Multiple scenes for varied testing
- Active personas

### 4. Environment Variables for Load Test

Create `wip/loadtest.env`:
```bash
# Target environment
BASE_URL=https://your-backend-url.railway.app
# Or for local testing:
# BASE_URL=http://localhost:8000

# Test user credentials (use a range)
TEST_USER_EMAIL_PREFIX=loadtest_user_
TEST_USER_EMAIL_DOMAIN=@test.com
TEST_USER_PASSWORD=testpassword123

# Simulation to test
TEST_SIMULATION_ID=1
TEST_COHORT_ID=1
```

---

## Test Scenarios

### Scenario 1: Authentication Load
**Purpose:** Verify login system handles concurrent authentications

| Metric | Target |
|--------|--------|
| Concurrent logins | 100 |
| Response time (p95) | < 2s |
| Error rate | < 1% |

### Scenario 2: Simulation Start (Begin Command)
**Purpose:** Test the "begin" command which bypasses queue

| Metric | Target |
|--------|--------|
| Concurrent begins | 100 |
| Response time (p95) | < 5s |
| Error rate | < 1% |

### Scenario 3: Chat Message Flow (Primary Test)
**Purpose:** Test full chat experience with streaming responses

| Metric | Target |
|--------|--------|
| Concurrent chats | 100 |
| Response time (p95) | < 30s (AI-dependent) |
| Error rate | < 5% |
| Queue utilization | > 50% under load |

### Scenario 4: Grading Requests
**Purpose:** Test grading endpoint under load

| Metric | Target |
|--------|--------|
| Concurrent grading | 50 |
| Response time (p95) | < 60s |
| Error rate | < 5% |

### Scenario 5: Mixed Workload (Realistic)
**Purpose:** Simulate realistic usage patterns

| User Type | Percentage | Behavior |
|-----------|------------|----------|
| Active chatters | 40% | Send messages every 10-30s |
| Readers | 30% | Read responses, occasional message |
| New users | 20% | Starting simulations |
| Grading | 10% | Completing and requesting grades |

---

## Locust Test Scripts

### File: `wip/locustfile.py`

```python
"""
Load Testing Script for n-aible Simulation Chat
Run with: locust -f wip/locustfile.py --host=https://your-backend.railway.app
"""

import os
import json
import random
import time
from locust import HttpUser, task, between, events
from dotenv import load_dotenv

# Load environment
load_dotenv("wip/loadtest.env")

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
TEST_USER_PREFIX = os.getenv("TEST_USER_EMAIL_PREFIX", "loadtest_user_")
TEST_USER_DOMAIN = os.getenv("TEST_USER_EMAIL_DOMAIN", "@test.com")
TEST_PASSWORD = os.getenv("TEST_USER_PASSWORD", "testpassword123")
TEST_SIMULATION_ID = int(os.getenv("TEST_SIMULATION_ID", "1"))

# Sample messages for chat testing
SAMPLE_MESSAGES = [
    "Hello, I'd like to start the simulation.",
    "Can you tell me more about this scenario?",
    "What should I do next?",
    "I think we should focus on the customer's needs.",
    "Let me try a different approach here.",
    "How would you respond to that objection?",
    "I want to negotiate better terms.",
    "What are the key points I should remember?",
    "Can we discuss the pricing options?",
    "I'd like to wrap up this conversation.",
]


class SimulationUser(HttpUser):
    """Simulates a user interacting with the simulation chat."""
    
    wait_time = between(5, 15)  # Wait 5-15 seconds between tasks
    
    def on_start(self):
        """Called when a user starts - handles login."""
        self.user_number = random.randint(1, 100)
        self.email = f"{TEST_USER_PREFIX}{self.user_number}{TEST_USER_DOMAIN}"
        self.token = None
        self.user_progress_id = None
        self.job_ids = []
        
        # Login
        self.login()
    
    def login(self):
        """Authenticate and get JWT token."""
        with self.client.post(
            "/api/auth/login",
            data={
                "username": self.email,
                "password": TEST_PASSWORD,
            },
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                response.success()
            else:
                response.failure(f"Login failed: {response.status_code}")
    
    def get_headers(self):
        """Get authorization headers."""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}
    
    @task(10)
    def send_chat_message(self):
        """Send a chat message (most common action)."""
        if not self.token or not self.user_progress_id:
            return
        
        message = random.choice(SAMPLE_MESSAGES)
        
        with self.client.post(
            "/api/simulation/linear-chat-stream",
            json={
                "user_progress_id": self.user_progress_id,
                "message": message,
            },
            headers=self.get_headers(),
            catch_response=True,
            timeout=60
        ) as response:
            if response.status_code == 200:
                # Streaming response - read chunks
                response.success()
            elif response.status_code == 202:
                # Queued response - save job_id for polling
                data = response.json()
                job_id = data.get("job_id")
                if job_id:
                    self.job_ids.append(job_id)
                response.success()
            else:
                response.failure(f"Chat failed: {response.status_code}")
    
    @task(3)
    def poll_job_status(self):
        """Poll for queued job completion."""
        if not self.token or not self.job_ids:
            return
        
        job_id = self.job_ids[0]  # Check oldest job
        
        with self.client.get(
            f"/api/simulation/job/{job_id}/status",
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                if status in ["completed", "failed"]:
                    self.job_ids.pop(0)  # Remove completed job
                response.success()
            else:
                response.failure(f"Poll failed: {response.status_code}")
    
    @task(2)
    def start_simulation(self):
        """Start or continue a simulation."""
        if not self.token:
            return
        
        with self.client.post(
            "/api/simulation/start",
            json={
                "simulation_id": TEST_SIMULATION_ID,
            },
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.user_progress_id = data.get("user_progress_id")
                response.success()
            elif response.status_code == 400:
                # Already started - that's fine
                response.success()
            else:
                response.failure(f"Start failed: {response.status_code}")
    
    @task(1)
    def begin_simulation(self):
        """Send 'begin' command (bypasses queue)."""
        if not self.token or not self.user_progress_id:
            return
        
        with self.client.post(
            "/api/simulation/linear-chat-stream",
            json={
                "user_progress_id": self.user_progress_id,
                "message": "begin",
            },
            headers=self.get_headers(),
            catch_response=True,
            timeout=30
        ) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"Begin failed: {response.status_code}")
    
    @task(1)
    def request_grading(self):
        """Request simulation grading."""
        if not self.token or not self.user_progress_id:
            return
        
        with self.client.get(
            f"/api/simulation/grade?user_progress_id={self.user_progress_id}",
            headers=self.get_headers(),
            catch_response=True,
            timeout=120
        ) as response:
            if response.status_code in [200, 202]:
                response.success()
            else:
                response.failure(f"Grading failed: {response.status_code}")


class QuickChatUser(HttpUser):
    """
    Fast-paced user that sends many messages quickly.
    Used to stress-test the queue system.
    """
    
    wait_time = between(2, 5)  # More aggressive timing
    weight = 1  # Lower weight than SimulationUser
    
    def on_start(self):
        self.user_number = random.randint(1, 100)
        self.email = f"{TEST_USER_PREFIX}{self.user_number}{TEST_USER_DOMAIN}"
        self.token = None
        self.user_progress_id = None
        self.login()
    
    def login(self):
        with self.client.post(
            "/api/auth/login",
            data={"username": self.email, "password": TEST_PASSWORD},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                self.token = response.json().get("access_token")
                response.success()
    
    def get_headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}
    
    @task
    def rapid_chat(self):
        """Send messages rapidly to stress-test queue."""
        if not self.token:
            return
        
        # First ensure we have a user_progress_id
        if not self.user_progress_id:
            resp = self.client.post(
                "/api/simulation/start",
                json={"simulation_id": TEST_SIMULATION_ID},
                headers=self.get_headers()
            )
            if resp.status_code == 200:
                self.user_progress_id = resp.json().get("user_progress_id")
        
        if self.user_progress_id:
            self.client.post(
                "/api/simulation/linear-chat-stream",
                json={
                    "user_progress_id": self.user_progress_id,
                    "message": random.choice(SAMPLE_MESSAGES),
                },
                headers=self.get_headers(),
                timeout=60
            )
```

---

## Running the Tests

### Step 1: Start with Low Load (Smoke Test)

```bash
cd n-aible_edtech_sims

# Activate virtual environment
source venv-loadtest/bin/activate

# Run smoke test: 5 users, 1 user/second spawn rate
locust -f wip/locustfile.py \
    --host=https://your-backend.railway.app \
    --users=5 \
    --spawn-rate=1 \
    --run-time=2m \
    --headless
```

### Step 2: Gradual Ramp-Up Test

```bash
# Ramp from 0 to 50 users over 5 minutes
locust -f wip/locustfile.py \
    --host=https://your-backend.railway.app \
    --users=50 \
    --spawn-rate=0.17 \
    --run-time=10m \
    --headless \
    --csv=wip/results/ramp50
```

### Step 3: Full 100 User Test

```bash
# Full load: 100 users
locust -f wip/locustfile.py \
    --host=https://your-backend.railway.app \
    --users=100 \
    --spawn-rate=2 \
    --run-time=15m \
    --headless \
    --csv=wip/results/full100
```

### Step 4: Interactive Web UI (Recommended for Debugging)

```bash
# Start Locust with web UI
locust -f wip/locustfile.py --host=https://your-backend.railway.app

# Open browser to http://localhost:8089
# Configure users and spawn rate interactively
```

---

## Metrics to Monitor During Tests

### 1. Locust Dashboard Metrics
- **Requests/second**: Should handle 3-10 RPS for chat
- **Response time (median)**: < 10s for chat, < 2s for other endpoints
- **Response time (p95)**: < 30s for chat
- **Failure rate**: < 5%

### 2. Railway Backend Logs (Watch For)

```bash
# Good signs:
[SIMULATION_WORKER] Starting simulation queue worker (WORKER_ID=0)
[SIMULATION_WORKER] Starting simulation queue worker (WORKER_ID=1)
[SIMULATION_WORKER] Starting simulation queue worker (WORKER_ID=2)
[QUEUE_DECISION] Using queue due to worker saturation
[DB_CONNECTION_TYPE] ✓ CONFIRMED: Using NullPool

# Warning signs:
[QUEUE_DECISION] Using queue due to queue backlog (length=15+)
Database connection pool usage HIGH
[REDIS] Connection error
[SIMULATION_WORKER] Too many consecutive errors
```

### 3. Railway Metrics Dashboard
- **CPU usage**: Should stay < 80% per replica
- **Memory usage**: Should stay < 70% per replica
- **Network**: Watch for connection errors

### 4. Neon Dashboard
- **Connections**: Should stay well under plan limit
- **Compute usage**: Watch for autoscaling triggers
- **Query latency**: p99 should stay < 100ms

### 5. OpenAI Dashboard
- **Rate limit usage**: Should stay under 50% of tier limit
- **Error rate**: Should be near 0%

---

## Success Criteria

### Pass ✅
| Metric | Threshold |
|--------|-----------|
| Chat response time (p95) | < 30 seconds |
| Error rate | < 5% |
| System stability | No crashes for 15 min |
| Queue processing | Jobs complete within 2 min |
| All 3 replicas | Stay healthy |

### Warning ⚠️
| Metric | Threshold |
|--------|-----------|
| Chat response time (p95) | 30-60 seconds |
| Error rate | 5-10% |
| Queue backlog | > 20 jobs |
| Memory usage | > 70% |

### Fail ❌
| Metric | Threshold |
|--------|-----------|
| Chat response time (p95) | > 60 seconds |
| Error rate | > 10% |
| System crashes | Any replica crashes |
| Database errors | Connection exhaustion |

---

## Troubleshooting Guide

### Issue: High Error Rate (> 5%)

**Check:**
1. Railway logs for specific errors
2. Database connection errors → Reduce pool size or upgrade Neon plan
3. Redis connection errors → Reduce `REDIS_MAX_CONNECTIONS`
4. Timeout errors → Increase timeout values

**Fix:**
```bash
# Reduce concurrency limits in Railway env vars
SIMULATION_MAX_STREAMS_PER_PROCESS=25
SIMULATION_MAX_AI_CALLS_PER_PROCESS=15
```

### Issue: Slow Response Times (> 30s)

**Check:**
1. OpenAI API latency (external)
2. Queue backlog length
3. Database query times

**Fix:**
- If queue-related: Increase `MAX_CONCURRENT_JOBS`
- If AI-related: Accept as external dependency
- If DB-related: Check Neon dashboard for slow queries

### Issue: Memory Exhaustion

**Check:**
1. Railway metrics for memory usage per replica
2. Number of active streams

**Fix:**
```bash
# Reduce stream limits
SIMULATION_MAX_STREAMS_PER_PROCESS=20
```

### Issue: One Replica Overwhelmed

**Check:**
1. Worker IDs in logs - are all 3 active?
2. Redis key distribution

**Fix:**
- Verify worker-specific Redis keys are working
- Check Railway load balancing

---

## Post-Test Analysis

### 1. Collect Results

```bash
# Locust generates CSV files
ls wip/results/
# full100_stats.csv
# full100_failures.csv
# full100_stats_history.csv
```

### 2. Generate Report

```python
import pandas as pd

# Load results
stats = pd.read_csv("wip/results/full100_stats.csv")
print(stats[["Name", "Request Count", "Failure Count", "Median Response Time", "95%"]])
```

### 3. Document Findings

Update this file with:
- [ ] Actual test date and duration
- [ ] Peak users achieved
- [ ] Key metrics observed
- [ ] Issues encountered
- [ ] Recommendations for production

---

## Test Execution Log

### Test Run #1
- **Date:** ____________
- **Duration:** ____________
- **Max Users:** ____________
- **Result:** ____________
- **Notes:** ____________

### Test Run #2
- **Date:** ____________
- **Duration:** ____________
- **Max Users:** ____________
- **Result:** ____________
- **Notes:** ____________

---

## Next Steps After Successful Test

1. [ ] Document final configuration values
2. [ ] Set up monitoring alerts in Railway
3. [ ] Create runbook for scaling issues
4. [ ] Schedule periodic load tests (monthly recommended)
5. [ ] Consider chaos engineering (replica failure simulation)

