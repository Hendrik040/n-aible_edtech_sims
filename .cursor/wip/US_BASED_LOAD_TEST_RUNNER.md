# US-Based Load Test Runner via GitHub Actions

## Status: PARKED
**Created:** 2025-12-28  
**Priority:** Medium  
**Effort:** Low-Medium  

---

## Problem Statement

Currently, load tests are run from Europe (developer's local machine) against infrastructure hosted on US West Coast:
- **Railway Backend:** US region
- **Neon Database:** `us-west-2`

This introduces **~400-500ms round-trip latency** per request, which:
1. Inflates response time measurements
2. Makes it harder to identify true backend bottlenecks
3. Doesn't reflect real-world US user experience (our primary market)

---

## Proposed Solution

Use **GitHub Actions** with a US-based runner to execute load tests. GitHub's default runners are hosted in Azure US regions, providing low-latency access to our US-based infrastructure.

---

## Benefits

| Benefit | Impact |
|---------|--------|
| **Accurate metrics** | Eliminate transatlantic latency from measurements |
| **Reproducible** | Same environment every time |
| **Automated** | Can run on schedule or PR triggers |
| **Free** | GitHub Actions free tier is sufficient |
| **CI/CD Integration** | Can block PRs if performance regresses |

---

## Implementation Plan

### Phase 1: Manual Trigger Workflow

Create a GitHub Actions workflow that can be manually triggered to run load tests.

#### File: `.github/workflows/load-test.yml`

```yaml
name: Load Test

on:
  workflow_dispatch:
    inputs:
      test_scenario:
        description: 'Test scenario to run'
        required: true
        default: 'chat_load_test'
        type: choice
        options:
          - chat_load_test
          - registration_load_test
          - full_e2e_load_test
      user_count:
        description: 'Number of concurrent users'
        required: true
        default: '50'
        type: string
      duration:
        description: 'Test duration (e.g., 5m, 10m)'
        required: true
        default: '5m'
        type: string
      target_environment:
        description: 'Target environment'
        required: true
        default: 'development'
        type: choice
        options:
          - development
          - staging

jobs:
  load-test:
    runs-on: ubuntu-latest  # US-based runner
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          cd backend/tests/load_testing
          pip install locust requests python-dotenv

      - name: Create environment file
        run: |
          cd backend/tests/load_testing
          cat > loadtest.env << EOF
          LOAD_TEST_URL=${{ secrets.LOAD_TEST_URL_${{ inputs.target_environment }} }}
          TEST_USER_PREFIX=loadtest_user_opt
          TEST_USER_DOMAIN=@testnew.com
          TEST_USER_PASSWORD=${{ secrets.TEST_USER_PASSWORD }}
          TEST_SIMULATION_ID=${{ secrets.TEST_SIMULATION_ID }}
          LOAD_TEST_ENVIRONMENT=${{ inputs.target_environment }}
          EOF

      - name: Run load test
        run: |
          cd backend/tests/load_testing
          python -m locust \
            -f scenarios/${{ inputs.test_scenario }}.py \
            --headless \
            -u ${{ inputs.user_count }} \
            -r 10 \
            -t ${{ inputs.duration }} \
            --html=reports/load_test_$(date +%Y%m%d_%H%M%S).html \
            --csv=reports/load_test_$(date +%Y%m%d_%H%M%S)

      - name: Upload test results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: load-test-results-${{ github.run_id }}
          path: backend/tests/load_testing/reports/
          retention-days: 30

      - name: Post summary to PR/Issue
        if: always()
        run: |
          echo "## Load Test Results" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "- **Scenario:** ${{ inputs.test_scenario }}" >> $GITHUB_STEP_SUMMARY
          echo "- **Users:** ${{ inputs.user_count }}" >> $GITHUB_STEP_SUMMARY
          echo "- **Duration:** ${{ inputs.duration }}" >> $GITHUB_STEP_SUMMARY
          echo "- **Environment:** ${{ inputs.target_environment }}" >> $GITHUB_STEP_SUMMARY
          echo "" >> $GITHUB_STEP_SUMMARY
          echo "See artifacts for detailed HTML report." >> $GITHUB_STEP_SUMMARY
```

---

### Phase 2: Scheduled Runs (Optional)

Add a cron schedule to run nightly performance tests:

```yaml
on:
  schedule:
    - cron: '0 6 * * *'  # 6 AM UTC = 10 PM PST (off-peak)
```

---

### Phase 3: PR Performance Gates (Optional)

Run a smaller load test on PRs that touch backend code:

```yaml
on:
  pull_request:
    paths:
      - 'backend/**'
```

With a performance regression check:

```yaml
- name: Check for regression
  run: |
    # Compare P95 response time against threshold
    P95=$(cat reports/*_stats.csv | grep "Aggregated" | cut -d',' -f9)
    THRESHOLD=5000  # 5 seconds
    if [ "$P95" -gt "$THRESHOLD" ]; then
      echo "❌ P95 response time ($P95 ms) exceeds threshold ($THRESHOLD ms)"
      exit 1
    fi
```

---

## Required GitHub Secrets

Add these secrets in GitHub repo settings → Secrets → Actions:

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `LOAD_TEST_URL_DEVELOPMENT` | Development backend URL | `https://backend-development-0519.up.railway.app` |
| `LOAD_TEST_URL_STAGING` | Staging backend URL | `https://backend-staging.up.railway.app` |
| `TEST_USER_PASSWORD` | Password for test users | `testpassword123` |
| `TEST_SIMULATION_ID` | ID of simulation to test | `96` |

---

## Usage

### Manual Trigger

1. Go to **Actions** tab in GitHub
2. Select **Load Test** workflow
3. Click **Run workflow**
4. Fill in parameters:
   - Test scenario
   - User count
   - Duration
   - Target environment
5. Click **Run workflow**

### View Results

1. Go to the completed workflow run
2. Download the **load-test-results** artifact
3. Open the HTML report in browser

---

## Cost Considerations

| Resource | Free Tier | Notes |
|----------|-----------|-------|
| GitHub Actions | 2,000 mins/month | ~400 load test runs |
| Artifact Storage | 500 MB | Reports are small (~100KB each) |

---

## Alternative Options (Not Recommended)

| Option | Pros | Cons |
|--------|------|------|
| AWS EC2 Spot Instance | Full control | Cost, complexity, maintenance |
| Render Background Worker | Simple | Additional service cost |
| Railway Cron Job | Same infra | Not designed for load testing |

---

## Next Steps When Implementing

1. [ ] Create `.github/workflows/load-test.yml`
2. [ ] Add GitHub secrets for test credentials
3. [ ] Test workflow manually
4. [ ] Document in team wiki
5. [ ] (Optional) Add scheduled runs
6. [ ] (Optional) Add PR performance gates

---

## Related Documents

- [Load Testing Implementation Plan](./user-load-testing.md)
- [TTFB Optimization Plan](./TTFB_OPTIMIZATION_PLAN.md)
- [Architecture Scaling Evaluation](./ARCHITECTURE_SCALING_EVALUATION.md)

