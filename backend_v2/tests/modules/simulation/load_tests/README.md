# Load Testing

Locust-based load tests for simulating student and professor users.

## Quick Start

### 1. Create Test Accounts

Create student accounts via invite link (recommended):

```bash
# Get an invite token first (see below)
python create_test_accounts.py --count 50 --role student --invite-token <token> --base-url http://localhost:8000
```

The script outputs account credentials to use with Locust.

### 2. Set Environment Variables

```bash
export BASE_URL=http://localhost:8000
export LOADTEST_STUDENT_EMAILS="student1@test.com,student2@test.com,..."
export LOADTEST_STUDENT_PASSWORDS="password1,password2,..."
export SIMULATION_ID=1  # ID of simulation to test
```

### 3. Run Load Tests

**Web UI (interactive):**
```bash
locust -f locustfile.py
# Open http://localhost:8089
```

**Headless (with reports):**
```bash
locust --headless \
  --html report.html \
  --csv results \
  --users 50 \
  --spawn-rate 5 \
  --run-time 5m \
  -f locustfile.py
```

## Helper Scripts

### Get Invite Token

```bash
python get_invite_token.py \
  --professor-email prof@example.com \
  --professor-password password \
  --base-url http://localhost:8000
```

### Check for Duplicates

```bash
python check_instance_duplicates.py
```

## Configuration

- `BASE_URL` - Backend API URL (default: http://localhost:8000)
- `SIMULATION_ID` - Simulation to test (default: 1)
- `LOADTEST_STUDENT_EMAILS` - Comma-separated student emails
- `LOADTEST_STUDENT_PASSWORDS` - Comma-separated passwords
- `LOADTEST_PROFESSOR_EMAILS` - Comma-separated professor emails (optional)
- `LOADTEST_PROFESSOR_PASSWORDS` - Comma-separated passwords (optional)
- `STUDENT_WEIGHT` - Weight for student users (default: 9)
- `PROFESSOR_WEIGHT` - Weight for professor users (default: 1)

**Important:** Number of users in Locust should match or be less than the number of test accounts created.

