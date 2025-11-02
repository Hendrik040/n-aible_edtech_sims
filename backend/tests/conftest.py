"""
Test configuration and fixtures for backend API tests
"""
import pytest
import asyncio
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import tempfile
import os
from unittest.mock import Mock, patch

from main import app
from database.connection import get_db
from database.models import Base, User, Scenario, Cohort, ProfessorStudentMessage
from utilities.auth import get_password_hash, create_access_token

# Test database URL - use in-memory SQLite for tests
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

# Create test engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create test database tables
Base.metadata.create_all(bind=engine)

def override_get_db():
    """Override database dependency for testing"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

# Override the database dependency
app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def client():
    """Create test client"""
    with TestClient(app) as c:
        yield c

@pytest.fixture
def db_session():
    """Create database session for testing"""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def test_professor(db_session):
    """Create test professor user"""
    professor = User(
        user_id="PROF_001",
        email="professor@test.com",
        full_name="Test Professor",
        username="testprof",
        password_hash=get_password_hash("testpass123"),
        role="professor",
        bio="Test professor bio",
        is_active=True,
        is_verified=True
    )
    db_session.add(professor)
    db_session.commit()
    db_session.refresh(professor)
    return professor

@pytest.fixture
def test_student(db_session):
    """Create test student user"""
    student = User(
        user_id="STU_001",
        email="student@test.com",
        full_name="Test Student",
        username="teststudent",
        password_hash=get_password_hash("testpass123"),
        role="student",
        bio="Test student bio",
        is_active=True,
        is_verified=True
    )
    db_session.add(student)
    db_session.commit()
    db_session.refresh(student)
    return student

@pytest.fixture
def test_admin(db_session):
    """Create test admin user"""
    admin = User(
        user_id="ADMIN_001",
        email="admin@test.com",
        full_name="Test Admin",
        username="testadmin",
        password_hash=get_password_hash("testpass123"),
        role="admin",
        bio="Test admin bio",
        is_active=True,
        is_verified=True
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)
    return admin

@pytest.fixture
def test_scenario(db_session, test_professor):
    """Create test scenario"""
    scenario = Scenario(
        unique_id="TEST_SCENARIO_001",
        title="Test Scenario",
        description="A test scenario for unit testing",
        challenge="Test challenge description",
        industry="Technology",
        learning_objectives=["Learn testing", "Understand scenarios"],
        student_role="Software Developer",
        status="active",
        is_public=True,
        is_draft=False,
        created_by=test_professor.id,
        category="Leadership",
        difficulty_level="beginner",
        estimated_duration=30
    )
    db_session.add(scenario)
    db_session.commit()
    db_session.refresh(scenario)
    return scenario

@pytest.fixture
def test_cohort(db_session, test_professor):
    """Create test cohort"""
    cohort = Cohort(
        cohort_id="COHORT_001",
        name="Test Cohort",
        description="A test cohort for unit testing",
        professor_id=test_professor.id,
        is_active=True
    )
    db_session.add(cohort)
    db_session.commit()
    db_session.refresh(cohort)
    return cohort

@pytest.fixture
def auth_headers_professor(test_professor):
    """Create auth headers for professor"""
    token = create_access_token(data={"sub": str(test_professor.id)})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def auth_headers_student(test_student):
    """Create auth headers for student"""
    token = create_access_token(data={"sub": str(test_student.id)})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def auth_headers_admin(test_admin):
    """Create auth headers for admin"""
    token = create_access_token(data={"sub": str(test_admin.id)})
    return {"Authorization": f"Bearer {token}"}

@pytest.fixture
def mock_redis():
    """Mock Redis for testing"""
    with patch('utilities.redis_manager.redis_manager') as mock:
        mock.is_available.return_value = True
        mock.get.return_value = None
        mock.set.return_value = True
        mock.delete.return_value = True
        mock.get_keys.return_value = []
        yield mock

@pytest.fixture
def mock_openai():
    """Mock OpenAI for testing"""
    with patch('api.simulation.openai.OpenAI') as mock:
        mock_instance = Mock()
        mock_instance.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content="Test AI response"))]
        )
        mock.return_value = mock_instance
        yield mock_instance

