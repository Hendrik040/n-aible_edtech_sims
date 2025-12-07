# Load Testing (feature/test-suite-auth branch)

## Overview

This load testing suite has been updated to work with the new modular backend architecture. Currently, only authentication endpoints are implemented and tested.

## What's Being Tested

The load tests now focus on:
- ✅ **User Registration** - `/api/auth/users/register`
- ✅ **User Login** - `/api/auth/users/login`
- ✅ **Auth Status Check** - `/api/auth/users/status`
- ✅ **User Logout** - `/api/auth/users/logout`
- ✅ **Email Validation** - `/api/auth/users/check-email`

## What's NOT Being Tested (Yet)

These endpoints will be added as the backend migration continues:
- ❌ Student cohorts, Professor cohorts, Notifications, Simulation instances, Publishing/scenarios

## Running Tests

### Quick Smoke Test (Recommended)
```bash
cd backend
./tests/load/run_smoke_test.sh
```

### Custom Tests
```bash
# Interactive mode with Web UI
locust -f tests/load/locustfile.py --host http://localhost:8000
# Open http://localhost:8089

# Headless mode (30 users, 2 minutes)
locust -f tests/load/locustfile.py --host http://localhost:8000 --users 30 --spawn-rate 5 --run-time 2m --headless
```

## Expected Results
- **Success Rate**: >95%
- **Average Response Time**: <200ms

## Notes
- Tests create unique users with random emails (`loadtest_XXXXX@loadtest.com`)
- Users are randomly assigned `student` or `professor` roles
- Auth uses HttpOnly cookies managed automatically
