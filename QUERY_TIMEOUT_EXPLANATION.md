# Why Query Timeouts Happen

## Root Causes

### 1. **Connection Pool Exhaustion** (Primary Cause)
Your system can create up to **150 connections** from a single Railway instance:
- Main SQLAlchemy engine: 70 pool_size + 80 max_overflow = 150 connections
- PGVector engine: Additional separate pool (default ~5-10 connections)
- Ad-hoc `SessionLocal()` calls: More connections per request

**Neon's Limits:**
- Free/Standard tiers: ~100 server connections
- With PgBouncer: Recommends small client-side pools (5-10) or NullPool

**What Happens:**
- 50+ concurrent users × 3 connections per request = 150+ connections needed
- Neon rejects new connections when limit is reached
- Queries wait in queue for available connections
- If `pool_timeout=30` seconds is exceeded → **QueryTimeoutError**

### 2. **Database Lock Contention**
- Multiple concurrent requests querying same `user_progress_id` + `scene_id`
- Without `session_id` filtering, queries compete for same rows
- Long-running transactions hold locks
- Other queries wait for locks to release → timeout

### 3. **Network Latency to Neon**
- Railway → Neon network can have variable latency
- Under load, network can become congested
- Slow connections cause queries to take longer
- Combined with connection pool exhaustion → cascading timeouts

### 4. **Database Server Overload**
- Neon can become slow under heavy load
- Many concurrent queries stress the database
- Query execution time increases
- Timeouts occur when queries exceed execution time limits

### 5. **Missing Indexes**
- Queries without proper indexes scan large tables
- `conversation_logs` table grows with usage
- Full table scans are slow
- Slow queries hold connections longer → more timeouts

## How Timeouts Manifest

1. **Connection Pool Timeout** (`pool_timeout=30s`):
   - All connections in use
   - New query waits 30 seconds for available connection
   - Times out → `TimeoutError`

2. **Query Execution Timeout** (via `execution_options(timeout=5)`):
   - Query takes longer than 5 seconds to execute
   - Database or network is slow
   - Times out → `OperationalError` or `TimeoutError`

3. **Connection Timeout** (`connect_timeout=10s`):
   - Can't establish new connection within 10 seconds
   - Database server is overloaded or unreachable
   - Times out → `OperationalError`

## Why 5-Second Query Timeout is Important

The 5-second timeout on memory loading queries prevents:
- **Cascading failures**: One slow query doesn't block all requests
- **Connection pool exhaustion**: Slow queries release connections faster
- **Platform hangs**: Requests fail fast instead of waiting indefinitely
- **Better user experience**: Users get error message instead of infinite wait

## Solutions Implemented

1. **Session Isolation**: `session_id` filtering reduces lock contention
2. **Query Timeouts**: 5-second timeout prevents hangs
3. **Proper Indexing**: Composite index on `(user_progress_id, scene_id, session_id)`
4. **Connection Pool Optimization**: Using NullPool for PgBouncer connections

## Monitoring

Watch for these indicators:
- High number of `TimeoutError` exceptions
- `pool_timeout` exceptions in logs
- Slow query logs from Neon
- Connection pool metrics showing 100% utilization
