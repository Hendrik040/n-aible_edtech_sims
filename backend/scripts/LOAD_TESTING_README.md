# Load Testing Guide

This guide explains how to test the platform with multiple concurrent users to verify the connection pool and query optimizations.

## Quick Start

### 1. Create Test Users

First, create test student accounts in your database:

```python
# You can use the register endpoint or create them directly in the database
# For 30-40 students, create accounts like:
# teststudent1@test.com, teststudent2@test.com, etc.
# All with password: testpass123
```

### 2. Run Basic Load Test

```bash
# Test simulation instances endpoint with 30 concurrent users
python scripts/load_test.py --users 30 --endpoint simulation-instances

# Test login endpoint with 50 concurrent users
python scripts/load_test.py --users 50 --endpoint login

# Test full user flow (login + get instances)
python scripts/load_test.py --users 40 --endpoint full-flow
```

### 3. Test Against Production

```bash
# Test against production URL
python scripts/load_test.py --users 30 --endpoint simulation-instances --url https://your-production-url.com
```

## Test Scenarios

### Scenario 1: Simulation Instances Endpoint (Optimized)
Tests the endpoint we optimized to fix N+1 queries:

```bash
python scripts/load_test.py --users 40 --endpoint simulation-instances
```

**What it tests:**
- Batch loading of instances (no N+1 queries)
- Connection pool handling
- Response times under load

**Expected results:**
- Success rate: >95%
- Average response time: <500ms
- P95 response time: <1s

### Scenario 2: Concurrent Logins
Tests authentication under load:

```bash
python scripts/load_test.py --users 50 --endpoint login
```

**What it tests:**
- Database connection pool during authentication
- Cookie setting under load
- Auth endpoint performance

### Scenario 3: Full User Flow
Simulates complete user journey:

```bash
python scripts/load_test.py --users 30 --endpoint full-flow
```

**What it tests:**
- Login → Get User → Get Simulation Instances
- End-to-end performance
- Connection pool across multiple requests

### Scenario 4: Sustained Load
Test connection pool over time:

```bash
python scripts/load_test.py --users 20 --endpoint concurrent-login --duration 60
```

**What it tests:**
- Connection pool stability
- Memory leaks
- Long-term performance

## Interpreting Results

### Good Results ✅
- Success rate: >95%
- Average response time: <500ms
- P95 response time: <1s
- No connection pool errors

### Warning Signs ⚠️
- Success rate: <95% → Connection pool may be too small
- Average response time: >2s → Queries may be slow
- P95 response time: >5s → Need query optimization
- Connection pool errors → Increase pool size

## Monitoring During Tests

While running load tests, monitor:

1. **Database Connection Pool:**
   ```sql
   -- Check active connections
   SELECT count(*) FROM pg_stat_activity WHERE datname = 'your_database';
   
   -- Check connection pool stats
   SELECT * FROM pg_stat_database WHERE datname = 'your_database';
   ```

2. **Application Logs:**
   - Watch for connection pool timeout errors
   - Monitor query execution times
   - Check for N+1 query patterns

3. **System Resources:**
   - CPU usage
   - Memory usage
   - Database CPU/memory

## Customizing Test Users

Edit `scripts/load_test.py` and update the `TEST_USERS` list:

```python
TEST_USERS = [
    {"email": "student1@test.com", "password": "password123"},
    {"email": "student2@test.com", "password": "password123"},
    # Add more users...
]
```

## Advanced Testing

### Test Specific Scenario

```bash
# Test with specific scenario ID
python scripts/load_test.py --users 30 --endpoint full-flow --scenario-id 22
```

### Gradual Ramp-up

Modify the script to gradually increase load:

```python
# In load_test.py, you can add:
for batch_size in [10, 20, 30, 40, 50]:
    # Run test with batch_size users
    ...
```

## Troubleshooting

### "Connection pool exhausted" errors
- Increase `pool_size` and `max_overflow` in `database/connection.py`
- Check for connection leaks (queries not closing)

### High response times
- Check for slow queries (add query logging)
- Verify indexes are being used
- Check for N+1 query problems

### Authentication failures
- Ensure test users exist in database
- Check cookie settings (domain, samesite)
- Verify JWT token expiration settings

