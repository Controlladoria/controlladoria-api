"""
Unit tests for Auth Router

Tests authentication endpoints:
- User registration
- Email verification
- Login (with and without MFA)
- MFA setup (TOTP and Email)
- Password reset
- Profile updates
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from database import User
from api import app

client = TestClient(app)


class TestRegistration:
    """Test user registration endpoint"""

    @patch("routers.auth.AuthService.register_user")
    def test_register_success(self, mock_register):
        """Test successful user registration"""
        # Mock return value
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.full_name = "Test User"
        mock_user.company_name = "Test Co"
        mock_user.cnpj = "12345678000190"
        mock_user.is_active = True
        mock_user.is_verified = False
        mock_user.created_at = datetime.utcnow()

        mock_tokens = MagicMock()
        mock_tokens.access_token = "test_access_token"
        mock_tokens.refresh_token = "test_refresh_token"

        mock_register.return_value = (mock_user, mock_tokens)

        # Make request
        response = client.post(
            "/auth/register",
            json={
                "email": "test@example.com",
                "password": "SecurePass123!",
                "full_name": "Test User",
                "company_name": "Test Co",
                "cnpj": "12345678000190",
                "agreed_to_terms": True,
                "agreed_to_privacy": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["full_name"] == "Test User"
        assert "access_token" in data
        assert "refresh_token" in data

    def test_register_missing_fields(self):
        """Test registration with missing required fields"""
        response = client.post(
            "/auth/register",
            json={
                "email": "test@example.com",
                # Missing password, full_name, etc.
            },
        )

        assert response.status_code == 422  # Validation error


class TestLogin:
    """Test user login endpoint"""

    @patch("routers.auth.AuthService.login_user")
    def test_login_success_no_mfa(self, mock_login):
        """Test successful login without MFA"""
        mock_tokens = MagicMock()
        mock_tokens.access_token = "test_access_token"
        mock_tokens.refresh_token = "test_refresh_token"
        mock_tokens.token_type = "bearer"

        mock_login.return_value = mock_tokens

        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "SecurePass123!",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "test_access_token"
        assert data["refresh_token"] == "test_refresh_token"

    @patch("routers.auth.AuthService.login_user")
    def test_login_mfa_required(self, mock_login):
        """Test login returns MFA required response"""
        # Mock MFA required HTTPException
        mock_login.side_effect = HTTPException(
            status_code=202,
            detail={
                "requires_mfa": True,
                "mfa_method": "totp",
                "temp_token": "temp_token_123",
            },
        )

        response = client.post(
            "/auth/login",
            json={
                "email": "test@example.com",
                "password": "SecurePass123!",
            },
        )

        # Should return MFA required (not raise exception)
        assert response.status_code == 202
        data = response.json()
        assert data["requires_mfa"] is True
        assert data["mfa_method"] == "totp"

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        with patch("routers.auth.AuthService.login_user") as mock_login:
            mock_login.side_effect = HTTPException(
                status_code=401, detail="Credenciais inválidas"
            )

            response = client.post(
                "/auth/login",
                json={
                    "email": "test@example.com",
                    "password": "WrongPassword",
                },
            )

            assert response.status_code == 401


class TestMFASetup:
    """Test MFA setup endpoints"""

    @patch("routers.auth.get_current_active_user")
    def test_setup_totp_mfa(self, mock_current_user):
        """Test TOTP MFA setup returns secret and provisioning URI"""
        mock_user = MagicMock(spec=User)
        mock_user.email = "test@example.com"
        mock_current_user.return_value = mock_user

        response = client.post("/auth/mfa/setup/totp")

        assert response.status_code == 200
        data = response.json()
        assert "secret" in data
        assert "provisioning_uri" in data
        assert "otpauth://" in data["provisioning_uri"]

    @patch("routers.auth.get_current_active_user")
    @patch("routers.auth.MFAService.verify_totp_code")
    @patch("routers.auth.MFAService.enable_totp_mfa")
    def test_enable_totp_mfa(self, mock_enable, mock_verify, mock_current_user):
        """Test enabling TOTP MFA after verification"""
        mock_user = MagicMock(spec=User)
        mock_user.email = "test@example.com"
        mock_current_user.return_value = mock_user
        mock_verify.return_value = True

        response = client.post(
            "/auth/mfa/enable",
            json={
                "secret": "JBSWY3DPEHPK3PXP",
                "code": "123456",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "backup_codes" in data
        assert len(data["backup_codes"]) == 10
        assert "message" in data
        mock_enable.assert_called_once()

    @patch("routers.auth.get_current_active_user")
    @patch("routers.auth.MFAService.enable_email_mfa")
    def test_enable_email_mfa(self, mock_enable, mock_current_user):
        """Test enabling Email MFA"""
        mock_user = MagicMock(spec=User)
        mock_user.email = "test@example.com"
        mock_user.mfa_enabled = False
        mock_current_user.return_value = mock_user

        response = client.post("/auth/mfa/enable-email")

        assert response.status_code == 200
        data = response.json()
        assert "backup_codes" in data
        assert len(data["backup_codes"]) == 10
        mock_enable.assert_called_once()


class TestPasswordReset:
    """Test password reset flow"""

    @patch("routers.auth.AuthService.request_password_reset")
    def test_request_password_reset(self, mock_request):
        """Test password reset request"""
        mock_request.return_value = "reset_token_123"

        response = client.post(
            "/auth/password-reset/request",
            json={"email": "test@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        # Should not reveal if email exists (security best practice)
        assert "If the email exists" in data["message"]

    @patch("routers.auth.AuthService.confirm_password_reset")
    def test_confirm_password_reset(self, mock_confirm):
        """Test password reset confirmation"""
        mock_confirm.return_value = None  # Success

        response = client.post(
            "/auth/password-reset/confirm",
            json={
                "token": "reset_token_123",
                "new_password": "NewSecurePass123!",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Password reset successful"
        mock_confirm.assert_called_once()


class TestUserProfile:
    """Test user profile endpoints"""

    @patch("routers.auth.get_current_active_user")
    def test_get_current_user(self, mock_current_user):
        """Test getting current user info"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_user.email = "test@example.com"
        mock_user.full_name = "Test User"
        mock_user.company_name = "Test Co"
        mock_user.is_active = True
        mock_user.is_verified = True
        mock_current_user.return_value = mock_user

        response = client.get("/auth/me")

        assert response.status_code == 200
        # Response model validation will happen automatically

    @patch("routers.auth.get_current_active_user")
    @patch("routers.auth.AuthService.update_user_profile")
    def test_update_user_profile(self, mock_update, mock_current_user):
        """Test updating user profile"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        updated_user = MagicMock(spec=User)
        updated_user.id = 1
        updated_user.full_name = "Updated Name"
        mock_update.return_value = updated_user

        response = client.patch(
            "/auth/me",
            json={"full_name": "Updated Name"},
        )

        assert response.status_code == 200
        mock_update.assert_called_once()


class TestEmailVerification:
    """Test email verification endpoints"""

    @patch("database.get_db")
    def test_verify_email_valid_token(self, mock_get_db):
        """Test email verification with valid token"""
        mock_db = MagicMock(spec=Session)
        mock_get_db.return_value.__enter__.return_value = mock_db

        mock_user = MagicMock(spec=User)
        mock_user.email = "test@example.com"
        mock_user.is_verified = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        response = client.get("/auth/verify-email?token=valid_token_123")

        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert mock_user.is_verified is True

    @patch("database.get_db")
    def test_verify_email_invalid_token(self, mock_get_db):
        """Test email verification with invalid token"""
        mock_db = MagicMock(spec=Session)
        mock_get_db.return_value.__enter__.return_value = mock_db
        mock_db.query.return_value.filter.return_value.first.return_value = None

        response = client.get("/auth/verify-email?token=invalid_token")

        assert response.status_code == 400


class TestTokenRefresh:
    """Test token refresh endpoint"""

    @patch("routers.auth.AuthService.refresh_access_token")
    def test_refresh_token_success(self, mock_refresh):
        """Test successful token refresh"""
        mock_tokens = MagicMock()
        mock_tokens.access_token = "new_access_token"
        mock_tokens.refresh_token = "new_refresh_token"
        mock_refresh.return_value = mock_tokens

        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "old_refresh_token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] == "new_access_token"

    @patch("routers.auth.AuthService.refresh_access_token")
    def test_refresh_token_invalid(self, mock_refresh):
        """Test token refresh with invalid token"""
        mock_refresh.side_effect = HTTPException(
            status_code=401, detail="Invalid refresh token"
        )

        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid_token"},
        )

        assert response.status_code == 401
