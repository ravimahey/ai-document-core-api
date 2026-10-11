import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.api.deps import (
    get_db,
    get_email_service_dep,
    get_llm_service_dep,
)
from app.db.base import Base
from app.main import app
from app.services.email import MockEmailService
from app.services.llm import MockLLMService

# In-memory SQLite engine shared across threads for testing
engine_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(
    bind=engine_test, autoflush=False, expire_on_commit=False
)


@pytest.fixture(autouse=True)
def setup_db() -> Generator[None]:
    """Create fresh tables for every test and drop them afterward."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db_session() -> Generator[Session]:
    """Yield a database session for test setup and verification."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_email() -> MockEmailService:
    """Fixture providing an in-memory mock email service."""
    return MockEmailService()


@pytest.fixture
def mock_llm() -> MockLLMService:
    """Fixture providing a mock LangChain / OpenAI LLM service."""
    return MockLLMService()


@pytest.fixture
def client(
    db_session: Session,
    mock_email: MockEmailService,
    mock_llm: MockLLMService,
) -> Generator[TestClient]:
    """TestClient with overridden database, email, and LLM dependencies."""

    def override_get_db() -> Generator[Session]:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_email_service() -> MockEmailService:
        return mock_email

    def override_llm_service() -> MockLLMService:
        return mock_llm

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_email_service_dep] = override_email_service
    app.dependency_overrides[get_llm_service_dep] = override_llm_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
