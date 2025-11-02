# Backend API Tests

This directory contains comprehensive unit tests for the backend API endpoints.

## Test Structure

```
tests/
├── __init__.py                 # Test package initialization
├── conftest.py                 # Test configuration and fixtures
├── run_tests.py               # Test runner script
├── README.md                  # This file
├── test_auth.py               # Authentication and user management tests
├── test_scenarios.py          # Scenario management tests
├── test_cohorts.py            # Cohort management tests
├── test_messages.py           # Messaging system tests
├── test_simulation.py         # Simulation engine tests
├── test_pdf_processing.py     # PDF processing tests
├── test_publishing.py         # Publishing and marketplace tests
├── test_oauth.py              # OAuth authentication tests
├── test_professor_endpoints.py # Professor-specific endpoint tests
├── test_student_endpoints.py  # Student-specific endpoint tests
└── test_integration.py        # Integration and workflow tests
```

## Test Coverage

The test suite covers:

### Core API Endpoints
- **Authentication**: User registration, login, logout, profile management
- **Scenarios**: CRUD operations, publishing, drafts, status management
- **Cohorts**: Educational group management, student enrollment
- **Messages**: Messaging system, notifications, threads
- **Simulation**: AI-powered simulations, progress tracking
- **PDF Processing**: File upload, parsing, progress tracking
- **Publishing**: Scenario marketplace, ratings, reviews
- **OAuth**: Google authentication integration

### Role-Based Endpoints
- **Professor**: Dashboard, analytics, invitations, notifications
- **Student**: Cohorts, simulations, progress, achievements
- **Admin**: Cache management, system administration

### Integration Tests
- Complete user workflows
- End-to-end API flows
- Error handling scenarios
- CORS and security testing

## Running Tests

### Prerequisites

Install test dependencies:
```bash
pip install pytest pytest-cov pytest-xdist
```

### Basic Usage

Run all tests:
```bash
python tests/run_tests.py
```

Run specific test file:
```bash
python tests/run_tests.py -k test_auth
```

Run tests with verbose output:
```bash
python tests/run_tests.py -v
```

Run tests with coverage report:
```bash
python tests/run_tests.py -c
```

Run tests in parallel:
```bash
python tests/run_tests.py -p
```

List all available tests:
```bash
python tests/run_tests.py --list
```

### Using pytest directly

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_auth.py

# Run tests with coverage
pytest tests/ --cov=. --cov-report=html

# Run tests in parallel
pytest tests/ -n auto

# Run specific test pattern
pytest tests/ -k "test_login"
```

## Test Configuration

### Database
- Tests use an in-memory SQLite database
- Each test gets a fresh database session
- No external database required

### Mocking
- Redis operations are mocked
- OpenAI API calls are mocked
- External service calls are mocked

### Fixtures
- `client`: FastAPI test client
- `db_session`: Database session
- `test_professor`: Professor user fixture
- `test_student`: Student user fixture
- `test_admin`: Admin user fixture
- `test_scenario`: Scenario fixture
- `test_cohort`: Cohort fixture
- `auth_headers_*`: Authentication headers for different user types

## Test Categories

### Unit Tests
- Individual endpoint testing
- Input validation
- Error handling
- Authentication and authorization

### Integration Tests
- Complete workflow testing
- Cross-endpoint functionality
- Database interactions
- External service integration

### Security Tests
- Authentication bypass attempts
- Authorization checks
- Input sanitization
- CORS validation

## Writing New Tests

### Test Naming Convention
- Test functions should start with `test_`
- Use descriptive names: `test_user_login_success`
- Group related tests in the same file

### Test Structure
```python
def test_endpoint_functionality(client: TestClient, auth_headers: dict):
    """Test description"""
    # Arrange
    data = {"key": "value"}
    
    # Act
    response = client.post("/endpoint", json=data, headers=auth_headers)
    
    # Assert
    assert response.status_code == 200
    assert response.json()["key"] == "value"
```

### Using Fixtures
```python
def test_with_fixtures(client: TestClient, test_professor, test_scenario):
    """Test using fixtures"""
    response = client.get(f"/scenarios/{test_scenario.id}")
    assert response.status_code == 200
```

### Mocking External Services
```python
@patch('api.simulation.openai.OpenAI')
def test_with_mock(mock_openai, client: TestClient):
    """Test with mocked external service"""
    mock_openai.return_value.chat.completions.create.return_value = Mock()
    # Test implementation
```

## Continuous Integration

### GitHub Actions Example
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov
      - name: Run tests
        run: python tests/run_tests.py -c
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure you're running tests from the backend directory
2. **Database Errors**: Check that test database is properly configured
3. **Mock Errors**: Verify mock patches are correctly applied
4. **Authentication Errors**: Ensure auth headers are properly set

### Debug Mode
Run tests with debug output:
```bash
pytest tests/ -v -s --tb=long
```

### Test Isolation
Each test runs in isolation with:
- Fresh database session
- Clean Redis state
- Reset mocks
- Independent test data

## Performance

### Test Execution Time
- Unit tests: ~2-5 seconds
- Integration tests: ~10-15 seconds
- Full test suite: ~30-60 seconds

### Parallel Execution
Use `-p` flag for parallel execution:
```bash
python tests/run_tests.py -p
```

### Coverage Reports
Coverage reports are generated in HTML format:
- `htmlcov/index.html` - Coverage report
- `coverage.xml` - XML format for CI/CD

## Contributing

When adding new tests:
1. Follow existing naming conventions
2. Use appropriate fixtures
3. Mock external dependencies
4. Test both success and failure cases
5. Update this README if adding new test categories

