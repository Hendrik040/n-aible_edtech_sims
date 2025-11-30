"""
Pytest Configuration and Fixtures

This file configures the test environment for the backend.
It sets up:
1. An in-memory SQLite database for isolated testing.
2. Database session fixtures that handle transaction rollbacks (keeping tests clean).
3. FastAPI TestClient fixtures (sync and async) with dependency overrides.
"""
import pytest
import sys
import os
import pytest_asyncio
from typing import AsyncGenerator, Generator

# --- PATH SETUP ---
# We need to ensure the 'backend' directory is in sys.path so we can import 'app', 'common', 'modules'.
# 'conftest.py' is in 'backend/tests/conftest.py'.
# os.path.dirname(__file__) -> .../backend/tests
# .. -> .../backend
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Prepend to sys.path to ensure our local packages are preferred over system/installed ones
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

try:
    # Import application components relative to 'backend/' path
    # We do this inside try-except to catch path issues early
    import common.db.base
    import app.main
except ImportError:
    # If short import fails, try adding the parent of backend to path (for 'backend.common...')
    # This is a fallback for environments where 'backend' is treated as a package
    root_path = os.path.abspath(os.path.join(backend_path, '..'))
    if root_path not in sys.path:
        sys.path.insert(0, root_path)

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.main import app
from common.db.base import Base
from common.db.connection import get_db

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    """
    Create the test database tables once for the session.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """
    Creates a fresh sqlalchemy session for each test that rolls back on teardown.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    
    yield session
    
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """
    Synchronous TestClient fixture.
    """
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def async_client(db_session: Session) -> AsyncGenerator[AsyncClient, None]:
    """
    Asynchronous httpx client fixture.
    """
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()
