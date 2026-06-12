import os
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Set testing environment variables
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/9"
os.environ["GEMINI_API_KEY"] = "mock-key"

from sqlalchemy.pool import StaticPool
from app.db.base import Base
from app.db.session import get_db
from app.main import app

# Create in-memory SQLite engine for tests with StaticPool
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """
    Creates clean tables for each test function and manages a database session.
    """
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    """
    FastAPI TestClient fixture with database dependency overridden.
    """
    def _get_db_override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@pytest.fixture(scope="function")
def mock_celery():
    """
    Mocks the process_transaction_file.delay method to prevent actual queue submission.
    """
    with patch("app.tasks.pipeline_tasks.process_transaction_file.delay") as mock_delay:
        yield mock_delay

@pytest.fixture(autouse=True)
def override_session_local():
    """
    Automatically patches SessionLocal across the app to use the test session factory.
    """
    with patch("app.tasks.pipeline_tasks.SessionLocal", TestingSessionLocal), \
         patch("app.db.session.SessionLocal", TestingSessionLocal):
        yield

