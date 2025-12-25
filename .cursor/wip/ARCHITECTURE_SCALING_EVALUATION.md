# Architecture Scaling Evaluation: 100 Concurrent Users

## Executive Summary

This document evaluates the n-aible backend architecture for supporting **100 concurrent users** who are actively using the platform simultaneously. Based on the code review, there are several potential bottlenecks and configuration issues to address.

---

## 🔴 Critical Issues (Fix Before Scaling)

### 1. Missing `numReplicas` in railway.toml

**Current State:**
```toml
# backend_railway.toml - NO numReplicas setting!
[deploy]
startCommand = "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
```

**Problem:** Without `numReplicas`, you're running a single container. One container cannot handle 100 concurrent users effectively.

**Recommendation:** Add to `backend_railway.toml`:
```toml
numReplicas = 3  # Start with 3 for 100 users
```

---

### 2. Database Connection Pool (NullPool with PgBouncer)

**Current State:** (`backend/common/db/core.py`)
```python
if is_pooled_connection:
    # Using NullPool for Neon pooled connection (PgBouncer)
    _engine_kwargs.update({
        "poolclass": NullPool,
        ...
    })
else:
    # Direct connections: pool_size=10, max_overflow=10 (20 total)
    pool_size = int(pool_size_env) if pool_size_env else 10
    max_overflow = int(max_overflow_env) if max_overflow_env else 10
```

**Analysis:**
- ✅ **Good:** If using Neon with PgBouncer, NullPool is correct
- ⚠️ **Risk:** If using direct PostgreSQL, 20 connections per replica × 3 replicas = 60 connections
- ⚠️ **Risk:** Neon's PgBouncer has limits (check your plan)

**Recommendations:**
1. **Verify your database plan's connection limit** (Neon free tier = 100 connections)
2. If using PgBouncer: Ensure Neon's pooler size > (replicas × expected concurrent DB ops)
3. If direct connections:
   ```bash
   # Set in Railway environment variables
   DB_POOL_SIZE=5
   DB_MAX_OVERFLOW=5
   # Per replica: 10 connections. 3 replicas = 30 total (safe for most plans)
   ```

---

### 3. Redis Connection Pool

**Current State:** (`backend/common/services/cache_service.py`)
```python
self.pool = redis.ConnectionPool.from_url(
    redis_url,
    max_connections=50,  # Per replica!
    ...
)
```

**Analysis:**
- ⚠️ **Risk:** 50 connections × 3 replicas = 150 Redis connections
- Most Redis providers limit to 100-500 connections (check your plan)

**Recommendation:**
```python
max_connections=20  # 20 × 3 replicas = 60 connections (safer)
```

Or set via environment variable (preferred):
```bash
# Add to Railway environment
REDIS_MAX_CONNECTIONS=20
```

---

## 🟡 Important Configurations to Review

### 4. Concurrency Limits (Currently Well-Configured)

**Current State:** (`backend/common/utils/concurrency.py`)
```python
_max_streams = _env_int("SIMULATION_MAX_STREAMS_PER_PROCESS", 40)
_max_ai_calls = _env_int("SIMULATION_MAX_AI_CALLS_PER_PROCESS", 25)
_max_vector_db_ops = _env_int("VECTOR_DB_MAX_CONCURRENT", 25)
```

**Analysis:**
- ✅ **Good:** Stream limit of 40 per replica is reasonable
- ✅ **Good:** AI call limit of 25 prevents OpenAI rate limiting
- ⚠️ **Note:** With 3 replicas: 120 total streams, 75 total AI calls

**Recommended Settings for 100 Users (3 Replicas):**
```bash
# Railway environment variables
SIMULATION_MAX_STREAMS_PER_PROCESS=35   # 35 × 3 = 105 total streams
SIMULATION_MAX_AI_CALLS_PER_PROCESS=20  # 20 × 3 = 60 total AI calls
VECTOR_DB_MAX_CONCURRENT=20             # 20 × 3 = 60 total vector ops
MAX_CONCURRENT_JOBS=5                   # Queue worker jobs per replica
```

---

### 5. Queue Decision Thresholds

**Current State:** (`backend/common/utils/queue_decision.py`)
```python
QUEUE_THRESHOLD_STREAMS = int(os.getenv("QUEUE_THRESHOLD_STREAMS", "8"))
QUEUE_THRESHOLD_LENGTH = int(os.getenv("QUEUE_THRESHOLD_LENGTH", "10"))
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))
```

**Analysis:**
- ✅ **Good:** Queue kicks in when < 8 stream slots available
- ⚠️ **Adjust:** With 100 users, may need higher thresholds

**Recommendation:**
```bash
QUEUE_THRESHOLD_STREAMS=10   # Start queuing when < 10 slots
QUEUE_THRESHOLD_LENGTH=15    # Allow slightly larger backlog
MAX_CONCURRENT_JOBS=5        # Keep at 5 per replica (15 total)
```

---

### 6. OpenAI API Rate Limits ✅ NOT A CONCERN

**Your Status:** **Usage Tier 4** 🎉
- $5,000/month usage limit
- ~10,000 RPM (requests per minute)
- Plenty of headroom for 100+ users

**Current State:** Multiple places have OpenAI semaphores:
- `concurrency.py`: 25 AI calls per replica
- `ai_extraction_service.py`: 2 concurrent for PDF processing
- `image_generation_service.py`: 10 concurrent for DALL-E

**Analysis:**
- 25 AI calls × 3 replicas = 75 concurrent
- At ~20 seconds per call = ~225 RPM (well under 10,000 RPM limit)
- **OpenAI is NOT your bottleneck!**

**Recommendation:**
- ✅ Keep current settings (25 AI calls per replica)
- Could even increase to 30 if needed for responsiveness
- Monitor costs at https://platform.openai.com/usage

---

### 7. Uvicorn Configuration

**Current State:** (`backend_railway.toml`)
```toml
startCommand = "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
```

**Analysis:**
- ⚠️ **Missing:** No `--workers` flag (defaults to 1)
- For async apps like FastAPI, 1 worker is usually fine
- BUT: no timeout configuration

**Recommendation:** Add timeouts for long-running requests:
```toml
startCommand = "uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-keep-alive 65 --log-level info --access-log"
```

---

## 🟢 What's Already Good

### ✅ Worker-Specific Redis Keys (Just Implemented)
- Each replica tracks its own in-progress jobs
- Restart of one replica doesn't affect others

### ✅ Async Architecture
- FastAPI with async endpoints
- Async streaming for chat responses
- Background task workers

### ✅ Queue System
- Jobs can be queued when under load
- Workers process jobs asynchronously
- Results stored in Redis for retrieval

### ✅ Connection Pooling Awareness
- Database pool monitoring with warnings at 80% capacity
- Redis connection pooling enabled
- NullPool for PgBouncer connections

---

## 📊 Recommended Configuration Summary

### Railway Environment Variables

```bash
# Replicas
numReplicas=3  # In railway.toml

# Database (if using direct connections, not PgBouncer)
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT=10

# Redis
REDIS_MAX_CONNECTIONS=20  # (need to add support for this)

# Concurrency Limits (per replica)
SIMULATION_MAX_STREAMS_PER_PROCESS=35
SIMULATION_MAX_AI_CALLS_PER_PROCESS=20
VECTOR_DB_MAX_CONCURRENT=20
MAX_CONCURRENT_JOBS=5

# Queue Thresholds
QUEUE_THRESHOLD_STREAMS=10
QUEUE_THRESHOLD_LENGTH=15
```

### Capacity Calculation (3 Replicas)

| Resource | Per Replica | Total (3 replicas) | 100 Users Need |
|----------|-------------|-------------------|----------------|
| Streams | 35 | 105 | ~60-80 active |
| AI Calls | 20 | 60 | ~30-50 concurrent |
| DB Connections | 10 | 30 | ~20-40 active |
| Redis Connections | 20 | 60 | ~30-50 active |
| Queue Workers | 5 | 15 | ~10-20 in queue |

---

## 🔧 Implementation Checklist

### Immediate (Before Scaling)

- [x] Add `numReplicas = 3` to `backend_railway.toml` ✅ DONE
- [x] Check OpenAI API tier and rate limits ✅ Tier 4 - plenty of headroom!
- [ ] Verify Neon/PostgreSQL connection limits
- [ ] Set environment variables in Railway (see above)

### Short-Term (Testing)

- [ ] Load test with 50 users, monitor:
  - Database connection pool warnings
  - Redis connection errors
  - OpenAI rate limit errors
  - Memory usage per replica
- [ ] Adjust concurrency limits based on test results
- [ ] Test replica restart (verify worker-specific keys work)

### Long-Term (Monitoring)

- [ ] Set up Railway observability dashboard
- [ ] Add custom metrics for:
  - Active streams per replica
  - Queue length and processing time
  - AI call latency and failures
- [ ] Configure alerts for high resource usage

---

## 📈 Scaling Beyond 100 Users

| Users | Replicas | Streams/Replica | AI Calls/Replica |
|-------|----------|-----------------|------------------|
| 50 | 2 | 40 | 25 |
| 100 | 3 | 35 | 20 |
| 200 | 5 | 35 | 18 |
| 500 | 10 | 30 | 15 |

**Key Insight:** As you scale, the bottleneck shifts from app capacity to:
1. **OpenAI API rate limits** - May need multiple API keys
2. **Database write throughput** - Consider read replicas
3. **Cost** - Each replica adds ~$10-20/month

---

## 🚨 Emergency Procedures

### If System Crashes Under Load

1. **Reduce replicas temporarily:**
   ```toml
   numReplicas = 1
   ```

2. **Force queue mode to slow things down:**
   ```bash
   FORCE_QUEUE_MODE=true
   ```

3. **Reduce concurrency limits:**
   ```bash
   SIMULATION_MAX_STREAMS_PER_PROCESS=20
   SIMULATION_MAX_AI_CALLS_PER_PROCESS=10
   ```

### If Database Connection Exhausted

1. Check Neon dashboard for connection count
2. If using direct connections:
   ```bash
   DB_POOL_SIZE=3
   DB_MAX_OVERFLOW=2
   ```
3. Consider enabling PgBouncer if not already

### If OpenAI Rate Limited

1. Check OpenAI dashboard for rate limit status
2. Reduce AI calls:
   ```bash
   SIMULATION_MAX_AI_CALLS_PER_PROCESS=10
   ```
3. Consider upgrading OpenAI tier

