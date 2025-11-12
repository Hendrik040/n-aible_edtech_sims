# Quick Load Testing Guide

## Step-by-Step Testing

### 1. Create Test Users

```bash
# Create 50 test students
cd backend
python scripts/create_test_users.py --count 50 --role student

# Or create 40 students with custom password
python scripts/create_test_users.py --count 40 --role student --password mytestpass
```

### 2. Start Your Backend Server

```bash
# In one terminal
cd backend
uvicorn main:app --reload --port 8000
```

### 3. Monitor Connection Pool (Optional - in another terminal)

```bash
# Monitor pool in real-time
cd backend
python scripts/monitor_pool.py

# Or monitor with custom interval
python scripts/monitor_pool.py --interval 2
```

### 4. Run Load Tests

```bash
# Test 1: Simulation Instances Endpoint (tests our N+1 fix)
python scripts/load_test.py --users 40 --endpoint simulation-instances

# Test 2: Login Endpoint (tests auth + connection pool)
python scripts/load_test.py --users 50 --endpoint login

# Test 3: Full User Flow (login → get instances)
python scripts/load_test.py --users 30 --endpoint full-flow

# Test 4: Sustained Load (60 seconds)
python scripts/load_test.py --users 20 --endpoint concurrent-login --duration 60
```

## Example Test Session

```bash
# Terminal 1: Start server
cd backend && uvicorn main:app --reload

# Terminal 2: Monitor pool
cd backend && python scripts/monitor_pool.py --interval 1

# Terminal 3: Run load test
cd backend && python scripts/load_test.py --users 40 --endpoint simulation-instances
```

## Expected Results

### Before Optimizations:
- ❌ Connection pool errors
- ❌ High response times (>2s)
- ❌ N+1 queries (many database queries)

### After Optimizations:
- ✅ No connection pool errors
- ✅ Fast response times (<500ms average)
- ✅ Batch queries (fewer database queries)

## Testing Production

```bash
# Test against production URL
python scripts/load_test.py \
  --users 30 \
  --endpoint simulation-instances \
  --url https://your-production-url.com
```

## Interpreting Results

### Good Performance ✅
- Success rate: >95%
- Avg response time: <500ms
- P95: <1s
- No connection errors

### Needs Attention ⚠️
- Success rate: <95% → Increase connection pool
- Avg response time: >2s → Check for slow queries
- P95: >5s → Optimize queries or add caching

