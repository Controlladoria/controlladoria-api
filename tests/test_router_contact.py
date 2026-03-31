"""
Unit tests for Contact Router

Tests contact form endpoints:
- Submit contact form (public, rate-limited)
- List submissions (admin only)
- Mark as read (admin only)
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from database import ContactSubmission
from api import app

client = TestClient(app)


class TestSubmitContactForm:
    """Test submitting contact form"""

    @patch("routers.contact.get_db")
    @patch("routers.contact.email_service.send_contact_notification")
    async def test_submit_contact_success(self, mock_email, mock_db):
        """Test successful contact form submission"""
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock contact submission
        mock_contact = MagicMock(spec=ContactSubmission)
        mock_contact.id = 1

        response = client.post(
            "/contact",
            json={
                "name": "Test User",
                "email": "test@example.com",
                "phone": "11999999999",
                "message": "Test message",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "submission_id" in data
        assert "Mensagem enviada com sucesso" in data["message"]

    @patch("routers.contact.get_db")
    def test_submit_contact_missing_fields(self, mock_db):
        """Test contact form with missing required fields"""
        response = client.post(
            "/contact",
            json={
                "name": "Test User",
                # Missing email and message
            },
        )

        assert response.status_code == 422  # Validation error

    @patch("routers.contact.get_db")
    @patch("routers.contact.email_service.send_contact_notification")
    async def test_submit_contact_email_fails(self, mock_email, mock_db):
        """Test that submission succeeds even if email fails"""
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock email failure
        mock_email.side_effect = Exception("Email service down")

        response = client.post(
            "/contact",
            json={
                "name": "Test User",
                "email": "test@example.com",
                "message": "Test message",
            },
        )

        # Should still succeed (email is non-critical)
        assert response.status_code == 200


class TestListContactSubmissions:
    """Test listing contact submissions (admin only)"""

    @patch("routers.contact.verify_api_key")
    @patch("routers.contact.get_db")
    def test_list_submissions(self, mock_db, mock_verify_key):
        """Test listing all contact submissions"""
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock submissions
        sub1 = MagicMock(spec=ContactSubmission)
        sub1.id = 1
        sub1.name = "User 1"
        sub1.email = "user1@test.com"
        sub1.phone = "11999999999"
        sub1.message = "Message 1"
        sub1.submitted_date = datetime.utcnow()
        sub1.read = 0
        sub1.replied = 0

        mock_query = mock_db_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 1
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            sub1
        ]

        response = client.get("/contact/submissions")

        assert response.status_code == 200
        data = response.json()
        assert "submissions" in data
        assert "total" in data
        assert data["total"] == 1

    @patch("routers.contact.verify_api_key")
    @patch("routers.contact.get_db")
    def test_list_unread_only(self, mock_db, mock_verify_key):
        """Test filtering for unread submissions only"""
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        mock_query = mock_db_session.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = (
            []
        )

        response = client.get("/contact/submissions?unread_only=true")

        assert response.status_code == 200
        # Verify filter was applied
        mock_query.filter.assert_called()


class TestMarkContactAsRead:
    """Test marking contact submissions as read"""

    @patch("routers.contact.verify_api_key")
    @patch("routers.contact.get_db")
    def test_mark_as_read_success(self, mock_db, mock_verify_key):
        """Test successfully marking submission as read"""
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock submission
        submission = MagicMock(spec=ContactSubmission)
        submission.id = 1
        submission.read = 0

        mock_db_session.query.return_value.filter.return_value.first.return_value = (
            submission
        )

        response = client.patch("/contact/submissions/1/mark-read")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Marked as read"
        assert data["id"] == 1
        assert submission.read == 1

    @patch("routers.contact.verify_api_key")
    @patch("routers.contact.get_db")
    def test_mark_as_read_not_found(self, mock_db, mock_verify_key):
        """Test marking non-existent submission as read"""
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        response = client.patch("/contact/submissions/999/mark-read")

        assert response.status_code == 404
