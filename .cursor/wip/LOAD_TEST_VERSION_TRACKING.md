# Load Test Version Tracking Implementation Plan

## Overview

Track which deployed version (commit, branch, tag) each Railway region (EU, US-DEV, US-EXP) is running when load tests execute. This enables thorough post-hoc analysis of performance regressions.

**Status:** 📋 Planned  
**Priority:** Medium  
**Estimated Effort:** 4-6 hours  
**Created:** 2025-12-28

---

## Problem Statement

The current load testing framework captures the **local git commit** (where tests are run from), but **NOT the deployed version on each Railway region**. These could be completely different!

### Current Implementation

```python
# backend/tests/load_testing/multi_region_benchmark.py (lines 924-947)
def get_git_info() -> Dict[str, Optional[str]]:
    """Get current git commit and branch."""
    git_info = {"commit": None, "branch": None}
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], ...)
        git_info["commit"] = result.stdout.strip()[:40]
        # ...
    return git_info
```

**Issue:** This only gets the commit from the machine running tests, not from each deployed region.

### What We Need

For each test run, capture:
- **Local commit** - Where tests were run from (keep existing)
- **Deployed commit per region** - What's actually running on EU/US-DEV/US-EXP
- **Commit message** - To quickly identify what changed
- **Git tag/version** - Semantic version (e.g., `v1.2.3`)
- **Branch** - Which branch was deployed

---

## Implementation Steps

### Step 1: Create Version Endpoint in Backend

**File:** `backend/app/routers/version.py` (new file)

```python
"""
Version endpoint for deployment tracking.

Returns current deployment version info from Railway environment variables.
"""
import os
from datetime import datetime
from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["system"])


def get_deployment_info():
    """
    Get deployment info from Railway environment variables.
    
    Railway automatically provides:
    - RAILWAY_GIT_COMMIT_SHA
    - RAILWAY_GIT_COMMIT_MESSAGE  
    - RAILWAY_GIT_BRANCH
    - RAILWAY_GIT_TAG
    - RAILWAY_DEPLOY_TIME
    """
    commit_sha = os.getenv("RAILWAY_GIT_COMMIT_SHA", "unknown")
    
    return {
        "commit": commit_sha,
        "commit_short": commit_sha[:7] if commit_sha != "unknown" else "unknown",
        "commit_message": os.getenv("RAILWAY_GIT_COMMIT_MESSAGE", "unknown")[:200],
        "branch": os.getenv("RAILWAY_GIT_BRANCH", "unknown"),
        "tag": os.getenv("APP_VERSION", os.getenv("RAILWAY_GIT_TAG", "untagged")),
        "deployed_at": os.getenv("RAILWAY_DEPLOY_TIME", datetime.utcnow().isoformat()),
        "environment": os.getenv("RAILWAY_ENVIRONMENT_NAME", "unknown"),
        "service": os.getenv("RAILWAY_SERVICE_NAME", "unknown"),
    }


@router.get("/version")
def get_version():
    """
    Return current deployment version info.
    
    Useful for:
    - Health checks
    - Load test tracking
    - Debugging which version is deployed
    """
    return get_deployment_info()
```

**Register in main.py:**
```python
from app.routers import version
app.include_router(version.router)
```

---

### Step 2: Update RegionResult Dataclass

**File:** `backend/tests/load_testing/multi_region_benchmark.py`

Add new fields to track deployed version:

```python
@dataclass
class RegionResult:
    """Results from a single region test."""
    region: str
    url: str
    timestamp: str
    duration_seconds: int
    total_users: int
    spawn_rate: float
    
    # ... existing metrics fields ...
    
    # NEW: Deployed version info (fetched from each region's /api/version)
    deployed_commit: Optional[str] = None
    deployed_commit_short: Optional[str] = None
    deployed_commit_message: Optional[str] = None
    deployed_branch: Optional[str] = None
    deployed_tag: Optional[str] = None
    deployed_at: Optional[str] = None
    
    # ... rest of existing fields ...
```

---

### Step 3: Add Version Fetch Function

**File:** `backend/tests/load_testing/multi_region_benchmark.py`

```python
def fetch_deployed_version(region: str, url: str) -> Dict[str, Optional[str]]:
    """
    Fetch version info from the deployed backend.
    
    Calls the /api/version endpoint on the target region to get
    the actual deployed commit, branch, tag, etc.
    
    Args:
        region: Region code (EU, US-DEV, US-EXP)
        url: Base URL of the backend
        
    Returns:
        Dict with deployed version info
    """
    version_info = {
        "deployed_commit": None,
        "deployed_commit_short": None,
        "deployed_commit_message": None,
        "deployed_branch": None,
        "deployed_tag": None,
        "deployed_at": None,
    }
    
    try:
        import requests
        response = requests.get(f"{url}/api/version", timeout=10)
        if response.status_code == 200:
            data = response.json()
            version_info["deployed_commit"] = data.get("commit")
            version_info["deployed_commit_short"] = data.get("commit_short")
            version_info["deployed_commit_message"] = data.get("commit_message", "")[:200]
            version_info["deployed_branch"] = data.get("branch")
            version_info["deployed_tag"] = data.get("tag")
            version_info["deployed_at"] = data.get("deployed_at")
            print(f"   ✓ {region} version: {version_info['deployed_commit_short']} ({version_info['deployed_branch']})")
        else:
            print(f"   ⚠ Could not fetch version from {region}: HTTP {response.status_code}")
    except Exception as e:
        print(f"   ⚠ Could not fetch version from {region}: {e}")
    
    return version_info
```

---

### Step 4: Integrate Version Fetch into Test Flow

**File:** `backend/tests/load_testing/multi_region_benchmark.py`

Update `run_single_region_test()` to fetch version before running:

```python
def run_single_region_test(
    region: str,
    users: int,
    spawn_rate: float,
    duration: str,
    scenario: str = "chat_load_test.py"
) -> RegionResult:
    """Run a load test against a single region."""
    
    # ... existing setup code ...
    
    # NEW: Fetch deployed version BEFORE running test
    print(f"   Fetching deployed version...")
    version_info = fetch_deployed_version(region, url)
    
    # ... run the test ...
    
    # When creating RegionResult, include version info:
    return RegionResult(
        region=region,
        url=url,
        # ... existing fields ...
        deployed_commit=version_info["deployed_commit"],
        deployed_commit_short=version_info["deployed_commit_short"],
        deployed_commit_message=version_info["deployed_commit_message"],
        deployed_branch=version_info["deployed_branch"],
        deployed_tag=version_info["deployed_tag"],
        deployed_at=version_info["deployed_at"],
    )
```

---

### Step 5: Update Database Schema

**SQL Migration for Neon Database:**

```sql
-- Run this on your LOADTEST_DATABASE_URL Neon database

-- Add new columns for deployed version tracking
ALTER TABLE load_test_runs 
ADD COLUMN IF NOT EXISTS deployed_commit VARCHAR(40),
ADD COLUMN IF NOT EXISTS deployed_commit_short VARCHAR(10),
ADD COLUMN IF NOT EXISTS deployed_commit_message VARCHAR(200),
ADD COLUMN IF NOT EXISTS deployed_branch VARCHAR(100),
ADD COLUMN IF NOT EXISTS deployed_tag VARCHAR(50),
ADD COLUMN IF NOT EXISTS deployed_at TIMESTAMP;

-- Rename existing columns for clarity (optional)
-- This distinguishes "where tests ran from" vs "what's deployed"
ALTER TABLE load_test_runs 
RENAME COLUMN git_commit TO local_git_commit;

ALTER TABLE load_test_runs 
RENAME COLUMN git_branch TO local_git_branch;

-- Add index for querying by deployed commit
CREATE INDEX IF NOT EXISTS idx_load_test_runs_deployed_commit 
ON load_test_runs(deployed_commit);

-- Add index for querying by deployed tag (version)
CREATE INDEX IF NOT EXISTS idx_load_test_runs_deployed_tag 
ON load_test_runs(deployed_tag);
```

---

### Step 6: Update Database Insert

**File:** `backend/tests/load_testing/multi_region_benchmark.py`

Update `save_results_to_database()`:

```python
cur.execute("""
    INSERT INTO load_test_runs (
        target_region, target_url, test_runner_location, environment,
        local_git_commit, local_git_branch,
        deployed_commit, deployed_commit_short, deployed_commit_message,
        deployed_branch, deployed_tag, deployed_at,
        test_scenario, configuration_notes,
        -- ... rest of existing columns ...
    ) VALUES (
        %s, %s, %s, %s,
        %s, %s,
        %s, %s, %s,
        %s, %s, %s,
        %s, %s,
        -- ... rest of values ...
    ) RETURNING id
""", (
    result.region,
    result.url,
    runner_location,
    environment,
    git_info["commit"],  # local
    git_info["branch"],  # local
    result.deployed_commit,
    result.deployed_commit_short,
    result.deployed_commit_message,
    result.deployed_branch,
    result.deployed_tag,
    result.deployed_at,
    # ... rest of values ...
))
```

---

### Step 7: Update JSON Output & Dashboard

Include deployed version info in:

1. **JSON results file** - Already handled by `asdict(r)` since we added fields to dataclass

2. **HTML Dashboard** - Add version info to the test info badges:

```python
# In generate_dashboard() function
<div class="test-info">
    <div class="info-badge">📅 <span>{timestamp}</span></div>
    <div class="info-badge">👥 <span>{test_config.total_users} users</span></div>
    <!-- NEW: Add deployed version badges per region -->
</div>

<!-- In the summary table, add columns for version info -->
<th>Deployed Commit</th>
<th>Branch</th>
<th>Tag</th>
```

---

## Railway Environment Variables Reference

Railway automatically provides these during deployment:

| Variable | Description | Example |
|----------|-------------|---------|
| `RAILWAY_GIT_COMMIT_SHA` | Full commit hash | `abc123def456...` |
| `RAILWAY_GIT_COMMIT_MESSAGE` | Commit message | `feat: Add streaming` |
| `RAILWAY_GIT_BRANCH` | Branch name | `main` |
| `RAILWAY_GIT_TAG` | Git tag if deployed from tag | `v1.2.3` |
| `RAILWAY_DEPLOY_TIME` | When deployed | ISO timestamp |
| `RAILWAY_ENVIRONMENT_NAME` | Environment name | `production` |
| `RAILWAY_SERVICE_NAME` | Service name | `backend` |

---

## Expected Output After Implementation

### JSON Results
```json
{
  "timestamp": "2025-12-28T13:18:08.207229",
  "results": [
    {
      "region": "EU",
      "url": "https://backend-europe.up.railway.app",
      "deployed_commit": "abc123def456789...",
      "deployed_commit_short": "abc123d",
      "deployed_commit_message": "feat: Optimize streaming TTFB (#142)",
      "deployed_branch": "main",
      "deployed_tag": "v1.2.3",
      "deployed_at": "2025-12-28T10:00:00Z",
      "total_requests": 50,
      "avg_response_time": 318.01,
      // ... other metrics
    },
    {
      "region": "US-DEV",
      "deployed_commit": "def789abc123...",  // Different commit!
      "deployed_commit_message": "fix: Auth token refresh (#141)",
      // ...
    }
  ]
}
```

### Console Output
```
🌍 Testing Region: EU
   URL: https://backend-europe.up.railway.app
   Fetching deployed version...
   ✓ EU version: abc123d (main) - v1.2.3
   Users: 30, Spawn Rate: 5/s, Duration: 2m
   Running test...
```

---

## Useful Queries After Implementation

```sql
-- Find all tests for a specific deployed commit
SELECT * FROM load_test_runs 
WHERE deployed_commit LIKE 'abc123%';

-- Compare performance across versions
SELECT 
    deployed_tag,
    target_region,
    AVG(avg_response_time_ms) as avg_response,
    AVG(failure_rate_percent) as avg_failures
FROM load_test_runs
WHERE deployed_tag IS NOT NULL
GROUP BY deployed_tag, target_region
ORDER BY deployed_tag DESC, target_region;

-- Find regressions: compare same region across deployments
SELECT 
    deployed_commit_short,
    deployed_commit_message,
    created_at,
    avg_response_time_ms,
    p95_response_time_ms,
    failure_rate_percent
FROM load_test_runs
WHERE target_region = 'EU'
ORDER BY created_at DESC
LIMIT 20;
```

---

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/routers/version.py` | **NEW** - Version endpoint |
| `backend/app/main.py` | Register version router |
| `backend/tests/load_testing/multi_region_benchmark.py` | Add version fetch, update RegionResult, update DB save |
| Neon Database | Run migration SQL |

---

## Testing Checklist

- [ ] Version endpoint returns correct Railway env vars
- [ ] Version endpoint works when env vars missing (graceful fallback)
- [ ] Benchmark fetches version before each region test
- [ ] JSON output includes deployed version info
- [ ] Database INSERT includes all new columns
- [ ] HTML dashboard shows version info
- [ ] Existing functionality not broken

---

## Related Files

- `backend/tests/load_testing/multi_region_benchmark.py` - Main benchmark runner
- `backend/tests/load_testing/config.py` - Test configuration
- `backend/tests/load_testing/loadtest.env` - Environment variables including `LOADTEST_DATABASE_URL`

