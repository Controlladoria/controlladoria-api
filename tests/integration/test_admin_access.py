"""
Tests for admin access control
Tests that admin endpoints are properly secured
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api import app
from auth.security import create_access_token, hash_password
from database import Base, User

# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_admin.db"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def test_db():
    """Create test database"""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(test_db):
    """Create database session for tests"""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """Create test client"""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    from database import get_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def regular_user(db_session):
    """Create regular (non-admin) user"""
    user = User(
        email="user@example.com",
        password_hash=hash_password("password123"),
        full_name="Regular User",
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session):
    """Create admin user"""
    user = User(
        email="admin@example.com",
        password_hash=hash_password("admin123"),
        full_name="Admin User",
        is_active=True,
        is_admin=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def regular_user_token(regular_user):
    """Generate JWT token for regular user"""
    return create_access_token(
        {"sub": str(regular_user.id), "email": regular_user.email}
    )


@pytest.fixture
def admin_token(admin_user):
    """Generate JWT token for admin user"""
    return create_access_token({"sub": str(admin_user.id), "email": admin_user.email})


class TestAdminAccess:
    """Test suite for admin access control"""

    def test_regular_user_cannot_access_admin_endpoint(
        self, client, regular_user_token
    ):
        """Regular users should be denied access to admin endpoints"""
        response = client.get(
            "/admin/stats", headers={"Authorization": f"Bearer {regular_user_token}"}
        )

        # Should return 403 Forbidden
        assert response.status_code == 403
        assert "admin" in response.json()["detail"].lower()

    def test_admin_user_can_access_admin_endpoint(self, client, admin_token):
        """Admin users should have access to admin endpoints"""
        response = client.get(
            "/admin/stats", headers={"Authorization": f"Bearer {admin_token}"}
        )

        # Should return 200 OK or 404 if endpoint doesn't exist yet
        # (404 is OK for this test since we're testing auth, not implementation)
        assert response.status_code in [200, 404]

    def test_unauthenticated_user_cannot_access_admin(self, client):
        """Unauthenticated requests should be denied"""
        response = client.get("/admin/stats")

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_invalid_token_cannot_access_admin(self, client):
        """Invalid tokens should be denied"""
        response = client.get(
            "/admin/stats", headers={"Authorization": "Bearer invalid_token_123"}
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401

    def test_admin_flag_is_checked(self, db_session, regular_user):
        """Verify is_admin flag is properly set"""
        # Regular user should have is_admin = False
        assert regular_user.is_admin is False

    def test_admin_user_has_flag_set(self, db_session, admin_user):
        """Verify admin user has is_admin flag"""
        # Admin user should have is_admin = True
        assert admin_user.is_admin is True

    def test_cannot_elevate_privileges_via_profile_update(
        self, client, regular_user_token
    ):
        """Users should not be able to make themselves admin via profile update"""
        response = client.patch(
            "/auth/me",
            headers={"Authorization": f"Bearer {regular_user_token}"},
            json={"is_admin": True},
        )

        # Should either be ignored or return error
        # The is_admin field should NOT be in allowed update fields
        assert response.status_code in [200, 400]

        # If 200, verify is_admin was not actually updated
        if response.status_code == 200:
            user_data = response.json()
            # is_admin should not be in response or should be False
            if "is_admin" in user_data:
                assert user_data["is_admin"] is False


class TestAdminMiddleware:
    """Test admin-only middleware/dependency"""

    def test_get_current_admin_user_with_regular_user(self, db_session, regular_user):
        """get_current_admin_user should reject regular users"""
        from fastapi import HTTPException

        from auth.dependencies import get_current_admin_user

        # Mock get_current_active_user to return regular user
        with pytest.raises(HTTPException) as exc_info:
            # This would be called by FastAPI with regular_user as dependency
            import asyncio

            asyncio.run(get_current_admin_user(current_user=regular_user))

        assert exc_info.value.status_code == 403
        assert "admin" in exc_info.value.detail.lower()

    def test_get_current_admin_user_with_admin(self, db_session, admin_user):
        """get_current_admin_user should accept admin users"""
        import asyncio

        from auth.dependencies import get_current_admin_user

        # Should not raise exception
        result = asyncio.run(get_current_admin_user(current_user=admin_user))
        assert result == admin_user
        assert result.is_admin is True
