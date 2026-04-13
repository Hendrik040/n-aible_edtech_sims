# Backend Tests

This directory contains all tests for the n-aible EdTech backend.

---

## 📁 Directory Structure

```
backend/tests/
├── README.md                           # This file
├── conftest.py                         # Pytest fixtures & configuration
│
├── modules/                            # Unit & Integration Tests
│   ├── auth/                           # Authentication tests
│   ├── cohorts/                        # Cohort management tests
│   ├── notifications/                  # Notification tests
│   ├── pdf_processing/                 # PDF parsing & AI extraction tests
│   ├── professor/                      # Professor dashboard tests
│   ├── publishing/                     # Simulation publishing tests
│   ├── simulation/                     # Simulation engine tests
│   └── student/                        # Student interface tests
│
├── load_testing/                       # Performance & Load Tests
│   ├── config.py                       # Configuration & region mapping
│   ├── loadtest.env                    # Your local config (gitignored)
│   ├── loadtest.env.example            # Example configuration
│   ├── multi_region_benchmark.py       # 🆕 Multi-region comparison tool
│   ├── locustfile.py                   # Main Locust entry point
│   ├── scenarios/                      # Test scenarios
│   │   ├── README.md                   # Detailed load testing docs
│   │   ├── chat_load_test.py           # AI chat simulation load test
│   │   └── registration_load_test.py   # User registration load test
│   ├── user_behaviors/                 # User behavior definitions
│   │   ├── base.py                     # Base authenticated user
│   │   ├── chat_user.py                # Chat simulation behavior
│   │   └── registration_user.py        # Registration behavior
│   └── reports/                        # Generated reports (gitignored)
│
└── test_utils/                         # Shared test utilities
    ├── __init__.py
    └── fixtures.py                     # Reusable fixtures
```

---

## 🧪 Unit & Integration Tests

### Running All Tests

```bash
cd backend
pytest tests/
```

### Running Specific Module Tests

```bash
# Auth tests
pytest tests/modules/auth/

# Simulation tests
pytest tests/modules/simulation/

# With verbose output
pytest tests/modules/auth/ -v
```

### Running with Coverage

```bash
pytest tests/ --cov=backend --cov-report=html
```

---

## 🚀 Load Testing

Load tests use [Locust](https://locust.io/) to simulate concurrent users.

### Quick Start

```bash
cd backend/tests/load_testing

# 1. Setup environment
cp loadtest.env.example loadtest.env
# Edit loadtest.env with your settings

# 2. Activate venv
source venv/bin/activate  # or your venv path

# 3. Install dependencies
pip install locust python-dotenv

# 4. Run a quick test
locust -f scenarios/chat_load_test.py --headless -u 10 -r 2 -t 1m
```

### Available Load Tests

| Scenario | Description | Command |
|----------|-------------|---------|
| **Registration** | Mass user registration | `locust -f scenarios/registration_load_test.py ...` |
| **Chat Simulation** | AI chat under load | `locust -f scenarios/chat_load_test.py ...` |
| **Multi-Region** | Compare EU vs US performance | `python multi_region_benchmark.py` |

### Multi-Region Benchmark (NEW)

Compare performance across different geographical regions:

```bash
# Test all 3 regions with default settings
python multi_region_benchmark.py

# Custom: specific regions, 50 users, 3 minutes
python multi_region_benchmark.py --regions EU US-DEV --users 50 --duration 3m

# Quick smoke test
python multi_region_benchmark.py --users 10 --duration 1m
```

**Outputs:**
- Interactive HTML dashboard with charts
- JSON results for analysis
- Console summary with winner

### Region Configuration

Set your target region in `loadtest.env`:

```env
TARGET_REGION=US-DEV   # Options: EU, US-DEV, US-EXP
```

| Region | URL | Notes |
|--------|-----|-------|
| EU | `backend-europe.up.railway.app` | European deployment |
| US-DEV | `backend-development-0519.up.railway.app` | US Development |
| US-EXP | `backend-experimental-246c.up.railway.app` | US Experimental |
| US-PROD | TBD | Production (coming soon) |
| US-STAG | TBD | Staging (coming soon) |

📚 **Full documentation:** See [`load_testing/scenarios/README.md`](load_testing/scenarios/README.md)

---

## ⚙️ Test Configuration

### Environment Variables

Tests use `loadtest.env` for configuration. Key variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `TARGET_REGION` | Target region code | `US-DEV` |
| `TEST_USER_PREFIX` | Test user email prefix | `loadtest_user_` |
| `TEST_USER_DOMAIN` | Test user email domain | `@test.com` |
| `TEST_USER_PASSWORD` | Password for test users | `testpassword123` |
| `TEST_SIMULATION_ID` | Simulation to test against | `96` |

### Pytest Fixtures

The `conftest.py` provides:
- `db_session` - Isolated database session with rollback
- `client` - Sync TestClient
- `async_client` - Async httpx client

---

## 📊 Viewing Results

### Unit Test Results

```bash
# Terminal output
pytest tests/ -v

# HTML report
pytest tests/ --html=report.html
```

### Load Test Results

Reports are saved to `load_testing/reports/`:

- `chat_load_test_YYYYMMDD_HHMMSS.html` - Individual test reports
- `multi_region_comparison_YYYYMMDD_HHMMSS.html` - Region comparison dashboards
- `multi_region_results_YYYYMMDD_HHMMSS.json` - Raw metrics data

---

## 🔧 Troubleshooting

### Common Issues

**"ModuleNotFoundError: No module named 'app'"**
```bash
# Ensure you're in the backend directory
cd backend
pytest tests/
```

**"Host not set" in load tests**
```bash
# Ensure TARGET_REGION or LOAD_TEST_URL is set in loadtest.env
```

**Load test shows 0 requests**
- Check if target server is running
- Verify credentials in `loadtest.env`
- Enable debug mode: `DEBUG_MODE=true`

---

## 📝 Adding New Tests

### Unit Tests

1. Create test file in appropriate `modules/` subdirectory
2. Name it `test_*.py`
3. Use fixtures from `conftest.py`

```python
# tests/modules/simulation/test_new_feature.py
def test_my_feature(client, db_session):
    response = client.get("/api/simulation/...")
    assert response.status_code == 200
```

### Load Test Scenarios

1. Create scenario in `load_testing/scenarios/`
2. Inherit from `BaseLoadTestUser`
3. Define tasks with `@task` decorator

```python
# load_testing/scenarios/my_load_test.py
from user_behaviors.base import BaseLoadTestUser
from locust import task

class MyLoadTestUser(BaseLoadTestUser):
    @task
    def my_test_task(self):
        self.client.get("/api/...")
```

---

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Locust Documentation](https://docs.locust.io/)
- [Full Load Testing Guide](load_testing/scenarios/README.md)

