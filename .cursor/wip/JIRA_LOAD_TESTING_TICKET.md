# Jira Ticket: Load Testing Initiative

---

## Summary
**ECS-XXX: Implement Load Testing for 100 Concurrent Users**

---

## Type
`Story` / `Task`

---

## Priority
`High`

---

## Labels
`performance`, `testing`, `infrastructure`, `scaling`

---

## Components
`Backend`, `Infrastructure`, `DevOps`

---

## Story Points
`8`

---

## Sprint
`[Current Sprint]`

---

## Description

### Background
Following the architecture scaling evaluation (ECS-117), we need to validate that the platform can handle **100 concurrent users** using the simulation chat experience simultaneously. Recent incidents showed system instability at 60 users, prompting infrastructure improvements including:
- Multi-replica deployment (3 replicas)
- Worker-specific Redis keys
- Optimized connection pooling (Neon PgBouncer)

### Objective
Create and execute a comprehensive load testing suite to verify system stability and identify bottlenecks before scaling to production with 100+ users.

### User Story
*As a DevOps engineer, I want to run load tests simulating 100 concurrent users so that we can validate system stability and identify performance bottlenecks before real users experience issues.*

### Technical Context
| Component | Configuration |
|-----------|---------------|
| Railway Replicas | 3 |
| Neon PostgreSQL | Launch plan, PgBouncer enabled |
| Redis | Railway managed, 20 connections/replica |
| OpenAI | Tier 4 (~10,000 RPM) |
| Concurrency | 35 streams/replica, 20 AI calls/replica |

---

## Acceptance Criteria

### Must Have ✅
- [ ] Load testing environment is set up with Locust
- [ ] 100 test user accounts created in staging/test database
- [ ] Smoke test passes (5 users, 2 minutes)
- [ ] Ramp-up test passes (50 users, 10 minutes)
- [ ] Full load test passes (100 users, 15 minutes)
- [ ] All success criteria met:
  - Chat response time (p95) < 30 seconds
  - Error rate < 5%
  - No replica crashes during 15-minute test
  - Queue jobs complete within 2 minutes

### Should Have 🔶
- [ ] Test results documented with metrics
- [ ] Bottlenecks identified and documented
- [ ] Recommendations for production scaling documented

### Nice to Have 💡
- [ ] Automated load test in CI/CD pipeline
- [ ] Grafana/monitoring dashboard for test metrics
- [ ] Chaos engineering test (replica failure simulation)

---

## Sub-Tasks

### 1. Setup (2 points)
- [ ] Create Python virtual environment for load testing
- [ ] Install Locust and dependencies
- [ ] Create `loadtest.env` configuration file
- [ ] Create 100 test user accounts in database

### 2. Test Script Development (3 points)
- [ ] Create `locustfile.py` with test scenarios
- [ ] Implement `SimulationUser` class (normal user behavior)
- [ ] Implement `QuickChatUser` class (stress test)
- [ ] Add job polling for queued responses
- [ ] Test script locally

### 3. Test Execution (2 points)
- [ ] Run smoke test (5 users)
- [ ] Run ramp-up test (50 users)
- [ ] Run full load test (100 users)
- [ ] Monitor Railway/Neon/OpenAI dashboards during tests

### 4. Analysis & Documentation (1 point)
- [ ] Collect and analyze test results
- [ ] Document bottlenecks found
- [ ] Create recommendations document
- [ ] Update architecture evaluation with findings

---

## Test Scenarios

| Scenario | Users | Duration | Primary Metric |
|----------|-------|----------|----------------|
| Smoke Test | 5 | 2 min | System stability |
| Ramp-Up | 50 | 10 min | Gradual load handling |
| Full Load | 100 | 15 min | Peak capacity |
| Stress Test | 150+ | 5 min | Breaking point (optional) |

---

## Success Metrics

| Metric | Pass ✅ | Warning ⚠️ | Fail ❌ |
|--------|---------|------------|---------|
| Chat p95 response | < 30s | 30-60s | > 60s |
| Error rate | < 5% | 5-10% | > 10% |
| Queue backlog | < 15 jobs | 15-25 jobs | > 25 jobs |
| Memory usage | < 70% | 70-85% | > 85% |

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| OpenAI rate limiting | High | Monitor usage, have fallback |
| Database connection exhaustion | High | Using PgBouncer, verified |
| Test affects production | Critical | Use staging environment |
| Unrealistic test patterns | Medium | Model after real user behavior |

---

## Dependencies

- [ ] ECS-117: Architecture scaling fixes deployed
- [ ] Access to staging/test environment
- [ ] Test user accounts created
- [ ] Railway metrics dashboard access
- [ ] Neon dashboard access

---

## Technical Notes

### Commands to Run

```bash
# Setup
pip install locust httpx python-dotenv

# Smoke test
locust -f wip/locustfile.py --host=$STAGING_URL --users=5 --spawn-rate=1 --run-time=2m --headless

# Full test
locust -f wip/locustfile.py --host=$STAGING_URL --users=100 --spawn-rate=2 --run-time=15m --headless --csv=results/full100
```

### Key Log Messages to Monitor

```
# Good
[SIMULATION_WORKER] Starting simulation queue worker (WORKER_ID=0)
[SIMULATION_WORKER] Starting simulation queue worker (WORKER_ID=1)
[SIMULATION_WORKER] Starting simulation queue worker (WORKER_ID=2)

# Warning
[QUEUE_DECISION] Using queue due to queue backlog (length=15+)
Database connection pool usage HIGH
```

---

## Definition of Done

- [ ] All acceptance criteria met
- [ ] Load test results reviewed by team
- [ ] No critical issues blocking 100-user capacity
- [ ] Documentation updated in `wip/user-load-testing.md`
- [ ] Findings shared with team

---

## Related Issues

- **ECS-117**: Fixing chat response error (architecture improvements)
- **Parent Epic**: Platform Scaling & Performance

---

## Attachments

- [ ] `wip/user-load-testing.md` - Detailed load testing plan
- [ ] `.cursor/ARCHITECTURE_SCALING_EVALUATION.md` - Architecture analysis
- [ ] Test results CSV files (after execution)

---

## Notes for QA/Review

- Test should be run against **staging environment**, not production
- Coordinate with team before running full 100-user test
- Monitor costs (OpenAI API usage) during testing
- Have rollback plan ready if issues discovered

---

*Created: [Date]*
*Reporter: [Your Name]*
*Assignee: [Assignee]*

