"""
Unit tests for Sessions Router

Tests session management endpoints:
- List active sessions
- Revoke specific session
- Revoke all sessions
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from database import User, UserSession
from api import app

client = TestClient(app)


class TestListSessions:
    """Test listing active sessions"""

    @patch("routers.sessions.get_current_active_user")
    @patch("routers.sessions.SessionManager.get_active_sessions")
    def test_list_active_sessions(self, mock_get_sessions, mock_current_user):
        """Test getting all active sessions for current user"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        # Mock sessions
        session1 = MagicMock(spec=UserSession)
        session1.id = "session_1"
        session1.device_type = "desktop"
        session1.device_os = "Windows"
        session1.device_name = "Chrome"
        session1.browser = "Chrome"
        session1.ip_address = "192.168.1.1"
        session1.created_at = datetime.utcnow()
        session1.last_activity = datetime.utcnow()
        session1.expires_at = datetime.utcnow() + timedelta(days=7)
        session1.is_active = True
        session1.is_trusted_device = False
        session1.trusted_until = None

        mock_get_sessions.return_value = [session1]

        response = client.get("/auth/sessions")

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["id"] == "session_1"
        assert data["sessions"][0]["device_type"] == "desktop"


class TestRevokeSession:
    """Test revoking specific session"""

    @patch("routers.sessions.get_current_active_user")
    @patch("routers.sessions.get_db")
    @patch("routers.sessions.SessionManager.revoke_session")
    def test_revoke_own_session(self, mock_revoke, mock_db, mock_current_user):
        """Test revoking own session"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        # Mock database session
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock session lookup
        mock_session = MagicMock(spec=UserSession)
        mock_session.id = "session_123"
        mock_session.user_id = 1
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_session
        )

        # Mock revoke success
        mock_revoke.return_value = True

        response = client.delete("/auth/sessions/session_123")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Sessão revogada com sucesso"

    @patch("routers.sessions.get_current_active_user")
    @patch("routers.sessions.get_db")
    def test_revoke_session_not_found(self, mock_db, mock_current_user):
        """Test revoking non-existent session"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
            None
        )

        response = client.delete("/auth/sessions/nonexistent_session")

        assert response.status_code == 404

    @patch("routers.sessions.get_current_active_user")
    @patch("routers.sessions.get_db")
    def test_revoke_other_users_session(self, mock_db, mock_current_user):
        """Test cannot revoke another user's session"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock session belonging to different user
        mock_session = MagicMock(spec=UserSession)
        mock_session.id = "session_123"
        mock_session.user_id = 999  # Different user
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = (
            mock_session
        )

        response = client.delete("/auth/sessions/session_123")

        assert response.status_code == 404  # Not found (security - don't reveal existence)


class TestRevokeAllSessions:
    """Test revoking all sessions"""

    @patch("routers.sessions.get_current_active_user")
    @patch("routers.sessions.SessionManager.revoke_all_sessions")
    def test_revoke_all_sessions(self, mock_revoke_all, mock_current_user):
        """Test revoking all sessions for current user"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_revoke_all.return_value = 3  # 3 sessions revoked

        response = client.delete("/auth/sessions")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 3
        assert "3 sessões revogadas" in data["message"]

    @patch("routers.sessions.get_current_active_user")
    @patch("routers.sessions.SessionManager.revoke_all_sessions")
    def test_revoke_all_sessions_except_current(self, mock_revoke_all, mock_current_user):
        """Test revoking all sessions except current"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_revoke_all.return_value = 2

        response = client.delete("/auth/sessions?except_current=true")

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
