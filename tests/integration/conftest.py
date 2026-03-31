"""
Integration test fixtures
Provides API client and authentication for integration tests
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Import app and database
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from api import app
from database import Base, get_db


# Test database setup
TEST_DATABASE_URL = "sqlite:///./test_integration.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for tests"""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create test database tables"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    """FastAPI test client"""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(client):
    """Create a test user"""
    user_data = {
        "email": f"test_{pytest.TestConfig.run_id}@example.com",
        "password": "TestPassword123!",
        "full_name": "Test User",
        "company_name": "Test Hospital",
    }

    response = client.post("/auth/register", json=user_data)
    if response.status_code == 200:
        return response.json()
    else:
        # User might already exist, try to login
        response = client.post(
            "/auth/login",
            json={"email": user_data["email"], "password": user_data["password"]},
        )
        if response.status_code == 200:
            return response.json()
        else:
            # Use default test credentials
            user_data["email"] = "test@example.com"
            response = client.post("/auth/register", json=user_data)
            if response.status_code == 200:
                return response.json()
            else:
                response = client.post(
                    "/auth/login",
                    json={"email": user_data["email"], "password": user_data["password"]},
                )
                return response.json()


@pytest.fixture
def auth_headers(test_user):
    """Authentication headers with JWT token"""
    access_token = test_user.get("access_token")
    if not access_token:
        pytest.skip("Could not obtain access token")

    return {"Authorization": f"Bearer {access_token}"}
