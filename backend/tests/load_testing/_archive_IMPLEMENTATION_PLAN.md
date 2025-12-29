# Load Testing Framework Implementation Plan

## Overview

This document outlines the implementation plan for integrating a load testing framework into `backend/tests/` to test the Railway deployment architecture for maximum user load.

---

## Proposed Directory Structure

```
backend/tests/
├── conftest.py                    # Existing - add load test fixtures
├── pytest.ini                     # NEW - pytest configuration
├── test_utils/
│   ├── __init__.py
│   ├── fixtures.py               # Existing - add shared fixtures
│   └── load_test_helpers.py      # NEW - load test utilities
├── modules/                       # Existing unit tests
│   └── ...
└── load_testing/                  # NEW - Load testing module
    ├── __init__.py
    ├── conftest.py               # Load test specific fixtures
    ├── config.py                 # Environment configuration
    ├── locustfile.py             # Main Locust test file
    ├── user_behaviors/           # User behavior classes
    │   ├── __init__.py
    │   ├── base_user.py          # Base authenticated user
    │   ├── simulation_user.py    # Normal simulation user
    │   ├── power_user.py         # High-activity user
    │   └── grading_user.py       # User requesting grades
    ├── scenarios/                 # Test scenarios
    │   ├── __init__.py
    │   ├── smoke_test.py         # 5 users, 2 min
    │   ├── ramp_up_test.py       # 50 users, gradual
    │   ├── full_load_test.py     # 100 users
    │   └── stress_test.py        # 150+ users (breaking point)
    ├── reports/                   # Test results (gitignored)
    │   └── .gitkeep
    └── README.md                  # Load testing documentation
```

---

## Implementation Steps

### Phase 1: Setup & Configuration (Day 1)

#### Step 1.1: Create Directory Structure

```bash
# Run from backend/tests/
mkdir -p load_testing/{user_behaviors,scenarios,reports}
touch load_testing/__init__.py
touch load_testing/user_behaviors/__init__.py
touch load_testing/scenarios/__init__.py
touch load_testing/reports/.gitkeep
```

#### Step 1.2: Add Dependencies to pyproject.toml

```toml
# Add to [project.optional-dependencies] or [tool.uv.dev-dependencies]
[project.optional-dependencies]
loadtest = [
    "locust>=2.20.0",
    "httpx>=0.25.0",
    "python-dotenv>=1.0.0",
    "pandas>=2.0.0",        # For result analysis
    "rich>=13.0.0",         # For CLI output
]
```

#### Step 1.3: Create Configuration File

**File: `backend/tests/load_testing/config.py`**

```python
"""
Load Testing Configuration

Manages environment-specific settings for load tests.
"""
import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class LoadTestConfig:
    """Configuration for load testing."""
    
    # Target environment
    base_url: str
    environment: str  # "local", "staging", "production"
    
    # Authentication
    test_user_prefix: str
    test_user_domain: str
    test_password: str
    
    # Test data
    simulation_id: int
    cohort_id: int
    
    # Timing
    min_wait: float  # seconds between requests
    max_wait: float
    
    # Limits
    max_users: int
    spawn_rate: float
    run_time: str  # e.g., "15m"
    
    @classmethod
    def from_env(cls, environment: str = "staging") -> "LoadTestConfig":
        """Create config from environment variables."""
        
        base_urls = {
            "local": "http://localhost:8000",
            "staging": os.getenv("STAGING_URL", "https://staging-backend.railway.app"),
            "production": os.getenv("PRODUCTION_URL", ""),  # Never run load tests on prod!
        }
        
        return cls(
            base_url=os.getenv("LOAD_TEST_URL", base_urls.get(environment, base_urls["staging"])),
            environment=environment,
            test_user_prefix=os.getenv("TEST_USER_PREFIX", "loadtest_user_"),
            test_user_domain=os.getenv("TEST_USER_DOMAIN", "@test.com"),
            test_password=os.getenv("TEST_PASSWORD", "testpassword123"),
            simulation_id=int(os.getenv("TEST_SIMULATION_ID", "1")),
            cohort_id=int(os.getenv("TEST_COHORT_ID", "1")),
            min_wait=float(os.getenv("MIN_WAIT", "5")),
            max_wait=float(os.getenv("MAX_WAIT", "15")),
            max_users=int(os.getenv("MAX_USERS", "100")),
            spawn_rate=float(os.getenv("SPAWN_RATE", "2")),
            run_time=os.getenv("RUN_TIME", "15m"),
        )


# Pre-configured profiles
PROFILES = {
    "smoke": LoadTestConfig(
        base_url="",  # Set at runtime
        environment="staging",
        test_user_prefix="loadtest_user_",
        test_user_domain="@test.com",
        test_password="testpassword123",
        simulation_id=1,
        cohort_id=1,
        min_wait=3,
        max_wait=10,
        max_users=5,
        spawn_rate=1,
        run_time="2m",
    ),
    "ramp": LoadTestConfig(
        base_url="",
        environment="staging",
        test_user_prefix="loadtest_user_",
        test_user_domain="@test.com",
        test_password="testpassword123",
        simulation_id=1,
        cohort_id=1,
        min_wait=5,
        max_wait=15,
        max_users=50,
        spawn_rate=0.5,
        run_time="10m",
    ),
    "full": LoadTestConfig(
        base_url="",
        environment="staging",
        test_user_prefix="loadtest_user_",
        test_user_domain="@test.com",
        test_password="testpassword123",
        simulation_id=1,
        cohort_id=1,
        min_wait=5,
        max_wait=15,
        max_users=100,
        spawn_rate=2,
        run_time="15m",
    ),
    "stress": LoadTestConfig(
        base_url="",
        environment="staging",
        test_user_prefix="loadtest_user_",
        test_user_domain="@test.com",
        test_password="testpassword123",
        simulation_id=1,
        cohort_id=1,
        min_wait=2,
        max_wait=5,
        max_users=150,
        spawn_rate=5,
        run_time="5m",
    ),
}


def get_config(profile: str = "full") -> LoadTestConfig:
    """Get configuration for a test profile."""
    config = PROFILES.get(profile, PROFILES["full"])
    # Override base_url from environment if set
    env_url = os.getenv("LOAD_TEST_URL")
    if env_url:
        config.base_url = env_url
    return config
```

---

### Phase 2: Base User Behaviors (Day 1-2)

#### Step 2.1: Base Authenticated User

**File: `backend/tests/load_testing/user_behaviors/base_user.py`**

```python
"""
Base User Behavior

Provides authentication and common functionality for all load test users.
"""
import random
import logging
from locust import HttpUser, between, events
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class BaseAuthenticatedUser(HttpUser):
    """
    Base class for authenticated load test users.
    
    Handles:
    - Login and token management
    - Common headers
    - Error handling
    """
    
    abstract = True  # Don't instantiate directly
    
    # Will be set from config
    host = ""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.user_number: int = random.randint(1, 100)
        self.email: str = ""
        self.user_progress_id: Optional[int] = None
        self.pending_jobs: list = []
    
    def on_start(self):
        """Called when user starts. Handles login."""
        from tests.load_testing.config import get_config
        config = get_config()
        
        self.email = f"{config.test_user_prefix}{self.user_number}{config.test_user_domain}"
        self._login(config.test_password)
    
    def _login(self, password: str) -> bool:
        """Authenticate and store token."""
        with self.client.post(
            "/api/auth/login",
            data={"username": self.email, "password": password},
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("access_token")
                self.user_id = data.get("user", {}).get("id")
                response.success()
                logger.info(f"User {self.email} logged in successfully")
                return True
            else:
                response.failure(f"Login failed: {response.status_code} - {response.text[:100]}")
                logger.error(f"Login failed for {self.email}: {response.status_code}")
                return False
    
    def get_headers(self) -> Dict[str, str]:
        """Get authorization headers."""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    def _handle_response(self, response, name: str) -> Optional[Dict[str, Any]]:
        """
        Handle API response with proper Locust reporting.
        
        Returns parsed JSON on success, None on failure.
        """
        if response.status_code == 200:
            response.success()
            return response.json()
        elif response.status_code == 202:
            # Queued response
            data = response.json()
            job_id = data.get("job_id")
            if job_id:
                self.pending_jobs.append(job_id)
            response.success()
            return data
        elif response.status_code == 401:
            # Token expired - try to re-login
            response.failure(f"{name}: Unauthorized")
            self._login_retry()
            return None
        else:
            response.failure(f"{name}: {response.status_code}")
            return None
    
    def _login_retry(self):
        """Retry login if token expired."""
        from tests.load_testing.config import get_config
        config = get_config()
        self._login(config.test_password)
```

#### Step 2.2: Simulation User

**File: `backend/tests/load_testing/user_behaviors/simulation_user.py`**

```python
"""
Simulation User Behavior

Simulates a typical user interacting with the simulation chat.
"""
import random
from locust import task, between
from .base_user import BaseAuthenticatedUser

# Sample messages that simulate real user behavior
SAMPLE_MESSAGES = [
    "Hello, I'd like to understand the situation better.",
    "Can you explain what's happening here?",
    "What options do I have?",
    "I think we should focus on the customer first.",
    "Let me try a different approach.",
    "How would you respond to that?",
    "I want to negotiate better terms.",
    "What are the key points I should remember?",
    "Can we discuss the pricing?",
    "I'd like to wrap up now.",
    "What's the best way to handle this objection?",
    "Tell me more about the customer's needs.",
    "I'll take the collaborative approach.",
    "Let's explore other alternatives.",
    "What would happen if I chose differently?",
]


class SimulationUser(BaseAuthenticatedUser):
    """
    Standard simulation user with realistic behavior patterns.
    
    Behavior distribution:
    - 50% chat messages
    - 20% job polling
    - 15% start/continue simulation
    - 10% begin command
    - 5% grading
    """
    
    wait_time = between(5, 15)  # 5-15 seconds between actions
    weight = 3  # Most common user type
    
    def on_start(self):
        """Login and start simulation."""
        super().on_start()
        self._ensure_simulation_started()
    
    def _ensure_simulation_started(self):
        """Make sure user has an active simulation."""
        from tests.load_testing.config import get_config
        config = get_config()
        
        with self.client.post(
            "/api/simulation/start",
            json={"simulation_id": config.simulation_id},
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.user_progress_id = data.get("user_progress_id")
                response.success()
            elif response.status_code == 400:
                # Already has progress - try to get it
                response.success()
                self._get_existing_progress()
    
    def _get_existing_progress(self):
        """Get existing user progress."""
        # This would need an endpoint to get current progress
        # For now, we'll handle this in the chat endpoint
        pass
    
    @task(10)
    def send_chat_message(self):
        """Send a chat message - most common action."""
        if not self.user_progress_id:
            self._ensure_simulation_started()
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
            timeout=60,
            name="/api/simulation/linear-chat-stream"
        ) as response:
            self._handle_response(response, "chat_message")
    
    @task(4)
    def poll_pending_jobs(self):
        """Poll for queued job completion."""
        if not self.pending_jobs:
            return
        
        job_id = self.pending_jobs[0]
        
        with self.client.get(
            f"/api/simulation/job/{job_id}/status",
            headers=self.get_headers(),
            catch_response=True,
            name="/api/simulation/job/[id]/status"
        ) as response:
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                if status in ["completed", "failed"]:
                    self.pending_jobs.pop(0)
                    # Optionally fetch result
                    if status == "completed":
                        self._fetch_job_result(job_id)
                response.success()
    
    def _fetch_job_result(self, job_id: str):
        """Fetch completed job result."""
        with self.client.get(
            f"/api/simulation/job/{job_id}/result",
            headers=self.get_headers(),
            catch_response=True,
            name="/api/simulation/job/[id]/result"
        ) as response:
            self._handle_response(response, "job_result")
    
    @task(3)
    def start_simulation(self):
        """Start or continue simulation."""
        from tests.load_testing.config import get_config
        config = get_config()
        
        with self.client.post(
            "/api/simulation/start",
            json={"simulation_id": config.simulation_id},
            headers=self.get_headers(),
            catch_response=True
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.user_progress_id = data.get("user_progress_id")
                response.success()
            elif response.status_code == 400:
                response.success()  # Already started
    
    @task(2)
    def send_begin_command(self):
        """Send 'begin' command (bypasses queue)."""
        if not self.user_progress_id:
            return
        
        with self.client.post(
            "/api/simulation/linear-chat-stream",
            json={
                "user_progress_id": self.user_progress_id,
                "message": "begin",
            },
            headers=self.get_headers(),
            catch_response=True,
            timeout=30,
            name="/api/simulation/linear-chat-stream [begin]"
        ) as response:
            self._handle_response(response, "begin_command")
    
    @task(1)
    def request_grading(self):
        """Request simulation grading."""
        if not self.user_progress_id:
            return
        
        with self.client.get(
            f"/api/simulation/grade?user_progress_id={self.user_progress_id}",
            headers=self.get_headers(),
            catch_response=True,
            timeout=120,
            name="/api/simulation/grade"
        ) as response:
            self._handle_response(response, "grading")
```

#### Step 2.3: Power User (Stress Test)

**File: `backend/tests/load_testing/user_behaviors/power_user.py`**

```python
"""
Power User Behavior

Aggressive user that sends many requests quickly to stress-test the system.
"""
import random
from locust import task, between
from .base_user import BaseAuthenticatedUser
from .simulation_user import SAMPLE_MESSAGES


class PowerUser(BaseAuthenticatedUser):
    """
    High-activity user for stress testing.
    
    Sends requests more frequently to test system limits.
    """
    
    wait_time = between(1, 3)  # Very short wait
    weight = 1  # Fewer of these users
    
    def on_start(self):
        super().on_start()
        self._quick_start()
    
    def _quick_start(self):
        """Quickly start simulation."""
        from tests.load_testing.config import get_config
        config = get_config()
        
        resp = self.client.post(
            "/api/simulation/start",
            json={"simulation_id": config.simulation_id},
            headers=self.get_headers()
        )
        if resp.status_code == 200:
            self.user_progress_id = resp.json().get("user_progress_id")
    
    @task
    def rapid_chat(self):
        """Send messages rapidly."""
        if not self.user_progress_id:
            self._quick_start()
            return
        
        message = random.choice(SAMPLE_MESSAGES)
        
        self.client.post(
            "/api/simulation/linear-chat-stream",
            json={
                "user_progress_id": self.user_progress_id,
                "message": message,
            },
            headers=self.get_headers(),
            timeout=60,
            name="/api/simulation/linear-chat-stream [power]"
        )
```

---

### Phase 3: Main Locust File (Day 2)

#### Step 3.1: Create Main Locustfile

**File: `backend/tests/load_testing/locustfile.py`**

```python
"""
Load Testing Entry Point

Main Locust file that orchestrates load testing.

Usage:
    # Smoke test
    locust -f tests/load_testing/locustfile.py --config tests/load_testing/scenarios/smoke.conf
    
    # Full test with web UI
    locust -f tests/load_testing/locustfile.py
    
    # Headless full test
    locust -f tests/load_testing/locustfile.py --headless -u 100 -r 2 -t 15m
"""
import os
import sys
import logging
from datetime import datetime

# Ensure backend is in path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from locust import events

# Import user behaviors
from tests.load_testing.user_behaviors.simulation_user import SimulationUser
from tests.load_testing.user_behaviors.power_user import PowerUser
from tests.load_testing.config import get_config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Event handlers for custom reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when test starts."""
    config = get_config()
    logger.info("=" * 60)
    logger.info(f"LOAD TEST STARTED")
    logger.info(f"  Target: {environment.host}")
    logger.info(f"  Environment: {config.environment}")
    logger.info(f"  Max Users: {config.max_users}")
    logger.info(f"  Started: {datetime.now().isoformat()}")
    logger.info("=" * 60)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when test stops."""
    logger.info("=" * 60)
    logger.info(f"LOAD TEST COMPLETED")
    logger.info(f"  Ended: {datetime.now().isoformat()}")
    
    # Log summary statistics
    stats = environment.stats
    logger.info(f"  Total Requests: {stats.total.num_requests}")
    logger.info(f"  Total Failures: {stats.total.num_failures}")
    logger.info(f"  Failure Rate: {stats.total.fail_ratio * 100:.2f}%")
    logger.info(f"  Avg Response Time: {stats.total.avg_response_time:.0f}ms")
    logger.info(f"  p95 Response Time: {stats.total.get_response_time_percentile(0.95):.0f}ms")
    logger.info("=" * 60)


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, **kwargs):
    """Called for each request - useful for detailed logging."""
    if exception:
        logger.warning(f"Request failed: {name} - {exception}")


# User classes to run (Locust auto-discovers these)
# The weight attribute determines the ratio of each user type
# SimulationUser has weight=3, PowerUser has weight=1
# So for every 4 users: 3 SimulationUsers, 1 PowerUser
```

---

### Phase 4: Scenario Configurations (Day 2-3)

#### Step 4.1: Smoke Test Configuration

**File: `backend/tests/load_testing/scenarios/smoke.conf`**

```ini
# Smoke Test Configuration
# Quick validation that system is working

[master]
locustfile = tests/load_testing/locustfile.py
headless = true
users = 5
spawn-rate = 1
run-time = 2m
html = tests/load_testing/reports/smoke_report.html
csv = tests/load_testing/reports/smoke
```

#### Step 4.2: Full Load Configuration

**File: `backend/tests/load_testing/scenarios/full_load.conf`**

```ini
# Full Load Test Configuration
# 100 concurrent users for 15 minutes

[master]
locustfile = tests/load_testing/locustfile.py
headless = true
users = 100
spawn-rate = 2
run-time = 15m
html = tests/load_testing/reports/full_load_report.html
csv = tests/load_testing/reports/full_load
```

---

### Phase 5: CLI Runner & Integration (Day 3)

#### Step 5.1: Create CLI Runner

**File: `backend/tests/load_testing/run_tests.py`**

```python
#!/usr/bin/env python
"""
Load Test Runner

Convenient CLI for running load tests with different profiles.

Usage:
    python -m tests.load_testing.run_tests smoke
    python -m tests.load_testing.run_tests full --url https://staging.railway.app
    python -m tests.load_testing.run_tests stress --users 150
"""
import os
import sys
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_path))

from tests.load_testing.config import PROFILES, get_config


def run_load_test(
    profile: str,
    url: str = None,
    users: int = None,
    spawn_rate: float = None,
    run_time: str = None,
    web_ui: bool = False,
):
    """Run a load test with the specified profile."""
    
    config = PROFILES.get(profile, PROFILES["full"])
    
    # Override from arguments
    if url:
        config.base_url = url
    if users:
        config.max_users = users
    if spawn_rate:
        config.spawn_rate = spawn_rate
    if run_time:
        config.run_time = run_time
    
    # Ensure base_url is set
    if not config.base_url:
        config.base_url = os.getenv("LOAD_TEST_URL", "http://localhost:8000")
    
    # Build locust command
    locust_file = Path(__file__).parent / "locustfile.py"
    report_dir = Path(__file__).parent / "reports"
    report_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    cmd = [
        "locust",
        "-f", str(locust_file),
        "--host", config.base_url,
    ]
    
    if not web_ui:
        cmd.extend([
            "--headless",
            "-u", str(config.max_users),
            "-r", str(config.spawn_rate),
            "-t", config.run_time,
            "--html", str(report_dir / f"{profile}_{timestamp}_report.html"),
            "--csv", str(report_dir / f"{profile}_{timestamp}"),
        ])
    
    print(f"\n{'='*60}")
    print(f"Running {profile.upper()} load test")
    print(f"  Target: {config.base_url}")
    print(f"  Users: {config.max_users}")
    print(f"  Spawn Rate: {config.spawn_rate}/s")
    print(f"  Duration: {config.run_time}")
    print(f"{'='*60}\n")
    
    # Set environment variables
    env = os.environ.copy()
    env["LOAD_TEST_URL"] = config.base_url
    env["TEST_USER_PREFIX"] = config.test_user_prefix
    env["TEST_USER_DOMAIN"] = config.test_user_domain
    env["TEST_PASSWORD"] = config.test_password
    env["TEST_SIMULATION_ID"] = str(config.simulation_id)
    
    # Run locust
    subprocess.run(cmd, env=env)


def main():
    parser = argparse.ArgumentParser(description="Run load tests")
    parser.add_argument(
        "profile",
        choices=["smoke", "ramp", "full", "stress"],
        help="Test profile to run"
    )
    parser.add_argument("--url", help="Target URL (overrides config)")
    parser.add_argument("--users", type=int, help="Number of users")
    parser.add_argument("--spawn-rate", type=float, help="Users spawned per second")
    parser.add_argument("--run-time", help="Test duration (e.g., 15m, 1h)")
    parser.add_argument("--web-ui", action="store_true", help="Start with web UI")
    
    args = parser.parse_args()
    
    run_load_test(
        profile=args.profile,
        url=args.url,
        users=args.users,
        spawn_rate=args.spawn_rate,
        run_time=args.run_time,
        web_ui=args.web_ui,
    )


if __name__ == "__main__":
    main()
```

---

### Phase 6: Documentation & Gitignore (Day 3)

#### Step 6.1: Update .gitignore

Add to `backend/.gitignore`:
```gitignore
# Load test reports
tests/load_testing/reports/*.html
tests/load_testing/reports/*.csv
tests/load_testing/reports/*_stats.csv
tests/load_testing/reports/*_failures.csv
tests/load_testing/reports/*_stats_history.csv
```

#### Step 6.2: Create README

**File: `backend/tests/load_testing/README.md`**

```markdown
# Load Testing Framework

This module provides load testing capabilities for the n-aible backend.

## Quick Start

```bash
# Install dependencies
cd backend
uv pip install locust httpx python-dotenv pandas rich

# Run smoke test (5 users)
python -m tests.load_testing.run_tests smoke --url https://your-staging.railway.app

# Run full load test (100 users)
python -m tests.load_testing.run_tests full --url https://your-staging.railway.app

# Run with web UI
python -m tests.load_testing.run_tests full --url https://your-staging.railway.app --web-ui
```

## Test Profiles

| Profile | Users | Duration | Purpose |
|---------|-------|----------|---------|
| smoke | 5 | 2 min | Quick validation |
| ramp | 50 | 10 min | Gradual load increase |
| full | 100 | 15 min | Target capacity test |
| stress | 150 | 5 min | Find breaking point |

## Configuration

Set these environment variables:

```bash
LOAD_TEST_URL=https://your-staging.railway.app
TEST_USER_PREFIX=loadtest_user_
TEST_USER_DOMAIN=@test.com
TEST_PASSWORD=testpassword123
TEST_SIMULATION_ID=1
```

## Reports

Reports are generated in `tests/load_testing/reports/`:
- HTML report with charts
- CSV files for detailed analysis

## Success Criteria

| Metric | Pass | Fail |
|--------|------|------|
| p95 response time | < 30s | > 60s |
| Error rate | < 5% | > 10% |
| System stability | No crashes | Any crash |
```

---

## Implementation Checklist

### Phase 1: Setup (2 hours)
- [ ] Create directory structure
- [ ] Add dependencies to pyproject.toml
- [ ] Create `config.py`

### Phase 2: User Behaviors (4 hours)
- [ ] Create `base_user.py`
- [ ] Create `simulation_user.py`
- [ ] Create `power_user.py`

### Phase 3: Main Locust File (2 hours)
- [ ] Create `locustfile.py`
- [ ] Add event handlers for reporting

### Phase 4: Scenario Configs (1 hour)
- [ ] Create smoke.conf
- [ ] Create full_load.conf
- [ ] Create other configs

### Phase 5: CLI Runner (2 hours)
- [ ] Create `run_tests.py`
- [ ] Test with local environment

### Phase 6: Documentation (1 hour)
- [ ] Update .gitignore
- [ ] Create README.md
- [ ] Document in main tests README

---

## Total Estimated Time: 12 hours (1.5 days)

---

## Dependencies on Other Work

1. **Test Users**: Need 100 test user accounts in database
2. **Test Simulation**: Need at least one published simulation with test cohort
3. **Staging Environment**: Need Railway staging environment URL
4. **Environment Variables**: Need proper configuration in staging


