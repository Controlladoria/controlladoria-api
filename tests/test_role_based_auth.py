"""
Tests for role-based authentication and permissions system

Tests cover:
- User registration with automatic owner role assignment
- Team invitation with different roles
- Role-based permission enforcement
- Audit log access restrictions
"""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# Import the FastAPI app and database models
from api import app
from database import get_db, User, Subscription, TeamInvitation, AuditLog
from auth.permissions import Permission, Role, has_permission, get_role_permissions, require_permission
from auth.service import create_access_token


# Test client fixture
@pytest.fixture
def client():
    return TestClient(app)


# Database fixture
@pytest.fixture
def db():
    db = next(get_db())
    try:
        yield db
    finally:
        # Clean up test data
        db.query(AuditLog).delete()
        db.query(TeamInvitation).delete()
        db.query(Subscription).delete()
        db.query(User).delete()
        db.commit()
        db.close()


# Helper to create a user with specific role
def create_test_user(db: Session, email: str, role: str = "owner", parent_user_id=None):
    """Create a test user with specified role"""
    user = User(
        email=email,
        full_name=f"Test User {email}",
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
        hashed_password="$2b$12$test_hash",  # Dummy hash
        role=role,
        parent_user_id=parent_user_id,
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Create subscription for owner users
    if role == "owner":
        subscription = Subscription(
            user_id=user.id,
            status="trial",
            max_users=1,
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=15),
        )
        db.add(subscription)
        db.commit()

    return user


def get_auth_header(user: User) -> dict:
    """Create auth header for a user"""
    token = create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


class TestUserRegistration:
    """Test user registration with automatic owner role assignment"""

    def test_registration_creates_owner_role(self, client, db):
        """Test that new users are automatically assigned owner role"""
        response = client.post("/auth/register", json={
            "email": "newowner@test.com",
            "password": "SecurePass123!",
            "full_name": "New Owner",
            "company_name": "New Company",
            "cnpj": "12.345.678/0001-90",
            "agreed_to_terms": True,
            "agreed_to_privacy": True,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "owner"
        assert data["email"] == "newowner@test.com"

        # Verify in database
        user = db.query(User).filter(User.email == "newowner@test.com").first()
        assert user is not None
        assert user.role == "owner"
        assert user.parent_user_id is None  # Owners have no parent

    def test_registration_creates_trial_subscription(self, client, db):
        """Test that registration creates a trial subscription with max_users=1"""
        response = client.post("/auth/register", json={
            "email": "trial@test.com",
            "password": "SecurePass123!",
            "full_name": "Trial User",
            "company_name": "Trial Company",
            "cnpj": "98.765.432/0001-10",
            "agreed_to_terms": True,
            "agreed_to_privacy": True,
        })

        assert response.status_code == 200
        user_data = response.json()

        # Check subscription
        user = db.query(User).filter(User.email == "trial@test.com").first()
        subscription = db.query(Subscription).filter(Subscription.user_id == user.id).first()

        assert subscription is not None
        assert subscription.status == "trial"
        assert subscription.max_users == 1


class TestRolePermissions:
    """Test role-based permission system"""

    def test_owner_has_all_permissions(self, db):
        """Test that owner role has all permissions"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        owner_perms = get_role_permissions(owner.role)

        # Owner should have all permissions
        assert Permission.ADMIN_VIEW_AUDIT_LOGS in owner_perms
        assert Permission.BILLING_MANAGE in owner_perms
        assert Permission.TEAM_INVITE in owner_perms
        assert Permission.DOCUMENTS_DELETE in owner_perms

    def test_admin_permissions(self, db):
        """Test that admin has most permissions except billing management"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        admin = create_test_user(db, "admin@test.com", role="admin", parent_user_id=owner.id)
        admin_perms = get_role_permissions(admin.role)

        # Admin should have audit logs
        assert Permission.ADMIN_VIEW_AUDIT_LOGS in admin_perms
        assert Permission.TEAM_INVITE in admin_perms
        assert Permission.DOCUMENTS_DELETE in admin_perms

        # Admin can VIEW billing but not MANAGE
        assert Permission.BILLING_VIEW in admin_perms
        assert Permission.BILLING_MANAGE not in admin_perms

    def test_accountant_permissions(self, db):
        """Test that accountant has document/report access but no team management"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        accountant = create_test_user(db, "accountant@test.com", role="accountant", parent_user_id=owner.id)
        accountant_perms = get_role_permissions(accountant.role)

        # Accountant should have document access
        assert Permission.DOCUMENTS_READ in accountant_perms
        assert Permission.DOCUMENTS_WRITE in accountant_perms
        assert Permission.DOCUMENTS_DELETE in accountant_perms
        assert Permission.REPORTS_ADVANCED in accountant_perms

        # But no team management or admin access
        assert Permission.TEAM_INVITE not in accountant_perms
        assert Permission.ADMIN_VIEW_AUDIT_LOGS not in accountant_perms
        assert Permission.BILLING_VIEW not in accountant_perms

    def test_viewer_read_only(self, db):
        """Test that viewer has read-only access"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        viewer = create_test_user(db, "viewer@test.com", role="viewer", parent_user_id=owner.id)
        viewer_perms = get_role_permissions(viewer.role)

        # Viewer can read
        assert Permission.DOCUMENTS_READ in viewer_perms
        assert Permission.REPORTS_VIEW in viewer_perms

        # But cannot write or delete
        assert Permission.DOCUMENTS_WRITE not in viewer_perms
        assert Permission.DOCUMENTS_DELETE not in viewer_perms
        assert Permission.TEAM_INVITE not in viewer_perms


class TestTeamInvitations:
    """Test team invitation flow with roles"""

    def test_owner_can_invite_with_any_role(self, client, db):
        """Test that owner can invite users with any role"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        headers = get_auth_header(owner)

        # Owner should be able to invite admin
        response = client.post("/team/invite",
            headers=headers,
            json={
                "email": "newadmin@test.com",
                "role": "admin",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "admin"

        # Verify invitation in database
        invitation = db.query(TeamInvitation).filter(
            TeamInvitation.email == "newadmin@test.com"
        ).first()
        assert invitation is not None
        assert invitation.role == "admin"

    def test_admin_cannot_invite_owner(self, client, db):
        """Test that admin cannot invite another owner"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        admin = create_test_user(db, "admin@test.com", role="admin", parent_user_id=owner.id)
        headers = get_auth_header(admin)

        response = client.post("/team/invite",
            headers=headers,
            json={
                "email": "newowner@test.com",
                "role": "owner",
            }
        )

        # Should fail - only owner can invite owner
        assert response.status_code == 403

    def test_accountant_cannot_invite(self, client, db):
        """Test that accountant cannot invite team members"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        accountant = create_test_user(db, "accountant@test.com", role="accountant", parent_user_id=owner.id)
        headers = get_auth_header(accountant)

        response = client.post("/team/invite",
            headers=headers,
            json={
                "email": "viewer@test.com",
                "role": "viewer",
            }
        )

        # Should fail - accountant doesn't have TEAM_INVITE permission
        assert response.status_code == 403

    def test_invitation_acceptance_assigns_correct_role(self, client, db):
        """Test that accepting invitation assigns the correct role"""
        owner = create_test_user(db, "owner@test.com", role="owner")

        # Create invitation
        invitation = TeamInvitation(
            email="invited@test.com",
            invited_by_user_id=owner.id,
            role="bookkeeper",
            token="test_token_123",
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        db.add(invitation)
        db.commit()

        # Accept invitation
        response = client.post("/team/accept-invitation/test_token_123", json={
            "email": "invited@test.com",
            "password": "SecurePass123!",
            "full_name": "Invited User",
            "company_name": owner.company_name,
            "cnpj": owner.cnpj,
            "agreed_to_terms": True,
            "agreed_to_privacy": True,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "bookkeeper"
        assert data["parent_user_id"] == owner.id


class TestAuditLogAccess:
    """Test audit log access restrictions"""

    def test_owner_can_access_audit_logs(self, client, db):
        """Test that owner can access audit logs"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        headers = get_auth_header(owner)

        response = client.get("/admin/audit-logs", headers=headers)
        assert response.status_code == 200

    def test_admin_can_access_audit_logs(self, client, db):
        """Test that admin can access audit logs"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        admin = create_test_user(db, "admin@test.com", role="admin", parent_user_id=owner.id)
        headers = get_auth_header(admin)

        response = client.get("/admin/audit-logs", headers=headers)
        assert response.status_code == 200

    def test_accountant_cannot_access_audit_logs(self, client, db):
        """Test that accountant cannot access audit logs"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        accountant = create_test_user(db, "accountant@test.com", role="accountant", parent_user_id=owner.id)
        headers = get_auth_header(accountant)

        response = client.get("/admin/audit-logs", headers=headers)
        assert response.status_code == 403

    def test_viewer_cannot_access_audit_logs(self, client, db):
        """Test that viewer cannot access audit logs"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        viewer = create_test_user(db, "viewer@test.com", role="viewer", parent_user_id=owner.id)
        headers = get_auth_header(viewer)

        response = client.get("/admin/audit-logs", headers=headers)
        assert response.status_code == 403

    def test_audit_logs_filtered_by_company(self, client, db):
        """Test that audit logs are filtered by company/organization"""
        # Create two separate organizations
        owner1 = create_test_user(db, "owner1@test.com", role="owner")
        owner2 = create_test_user(db, "owner2@test.com", role="owner")

        # Create audit logs for both owners
        log1 = AuditLog(
            user_id=owner1.id,
            action="create",
            entity_type="document",
            entity_id=1,
            changes_summary="Test log 1",
        )
        log2 = AuditLog(
            user_id=owner2.id,
            action="create",
            entity_type="document",
            entity_id=2,
            changes_summary="Test log 2",
        )
        db.add_all([log1, log2])
        db.commit()

        # Owner1 should only see their own logs
        headers = get_auth_header(owner1)
        response = client.get("/admin/audit-logs", headers=headers)
        assert response.status_code == 200
        data = response.json()

        # Should only see log1, not log2
        log_user_ids = [log["user_id"] for log in data["logs"]]
        assert owner1.id in log_user_ids
        assert owner2.id not in log_user_ids


class TestPermissionHelpers:
    """Test permission helper functions"""

    def test_has_permission_returns_true_for_valid_permission(self, db):
        """Test that has_permission returns True when user has permission"""
        owner = create_test_user(db, "owner@test.com", role="owner")

        assert has_permission(owner, Permission.ADMIN_VIEW_AUDIT_LOGS) is True
        assert has_permission(owner, Permission.BILLING_MANAGE) is True

    def test_has_permission_returns_false_for_invalid_permission(self, db):
        """Test that has_permission returns False when user lacks permission"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        viewer = create_test_user(db, "viewer@test.com", role="viewer", parent_user_id=owner.id)

        assert has_permission(viewer, Permission.ADMIN_VIEW_AUDIT_LOGS) is False
        assert has_permission(viewer, Permission.TEAM_INVITE) is False

    def test_require_permission_raises_exception(self, db):
        """Test that require_permission raises 403 when user lacks permission"""
        owner = create_test_user(db, "owner@test.com", role="owner")
        viewer = create_test_user(db, "viewer@test.com", role="viewer", parent_user_id=owner.id)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            require_permission(viewer, Permission.ADMIN_VIEW_AUDIT_LOGS)

        assert exc_info.value.status_code == 403
