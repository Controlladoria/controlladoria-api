"""
Tests for email service
Tests email sending functionality with Resend
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from email_service import EmailService

# Mock resend for unit testing - no real API key needed
try:
    import resend
    from config import settings
except ImportError:
    pytest.skip("resend package not installed", allow_module_level=True)


class TestEmailService:
    """Test suite for EmailService"""

    @pytest.fixture
    def email_service(self):
        """Create email service instance"""
        return EmailService()

    @pytest.mark.asyncio
    async def test_send_welcome_email(self, email_service):
        """Test sending welcome email"""
        with patch("resend.Emails.send") as mock_send:
            mock_send.return_value = {"id": "email_123"}

            result = await email_service.send_welcome_email(
                to="test@example.com", user_name="João Silva", trial_days=15
            )

            assert result is True
            mock_send.assert_called_once()

            # Verify email parameters
            call_args = mock_send.call_args[0][0]
            assert call_args["to"] == ["test@example.com"]
            assert "Bem-vindo" in call_args["subject"]
            assert "João Silva" in call_args["html"]
            assert "15 dias" in call_args["html"]

    @pytest.mark.asyncio
    async def test_send_password_reset_email(self, email_service):
        """Test sending password reset email"""
        with patch("resend.Emails.send") as mock_send:
            mock_send.return_value = {"id": "email_456"}

            result = await email_service.send_password_reset_email(
                to="test@example.com", token="abc123", user_name="Maria Santos"
            )

            assert result is True
            mock_send.assert_called_once()

            # Verify reset link contains token
            call_args = mock_send.call_args[0][0]
            assert "abc123" in call_args["html"]
            assert "Maria Santos" in call_args["html"]
            assert "Redefinir Senha" in call_args["subject"]

    @pytest.mark.asyncio
    async def test_send_contact_notification(self, email_service):
        """Test sending contact form notification"""
        with patch("resend.Emails.send") as mock_send:
            mock_send.return_value = {"id": "email_789"}

            result = await email_service.send_contact_notification(
                admin_email="admin@controlladoria.com.br",
                name="Cliente Teste",
                email="cliente@empresa.com",
                phone="(11) 98765-4321",
                message="Gostaria de mais informações",
            )

            assert result is True
            mock_send.assert_called_once()

            # Verify contact details in email
            call_args = mock_send.call_args[0][0]
            assert call_args["to"] == ["admin@controlladoria.com.br"]
            assert "Cliente Teste" in call_args["html"]
            assert "cliente@empresa.com" in call_args["html"]
            assert "(11) 98765-4321" in call_args["html"]
            assert "Gostaria de mais informações" in call_args["html"]

            # Verify reply-to is set to customer email
            assert call_args["reply_to"] == ["cliente@empresa.com"]

    @pytest.mark.asyncio
    async def test_email_failure_handling(self, email_service):
        """Test email sending failure is handled gracefully"""
        with patch("resend.Emails.send") as mock_send:
            mock_send.side_effect = Exception("SMTP connection failed")

            result = await email_service.send_welcome_email(
                to="test@example.com", user_name="Test User", trial_days=15
            )

            # Should return False on failure, not raise exception
            assert result is False

    @pytest.mark.asyncio
    async def test_resend_not_available(self):
        """Test behavior when Resend is not configured"""
        with patch("email_service.RESEND_AVAILABLE", False):
            service = EmailService()

            result = await service.send_welcome_email(
                to="test@example.com", user_name="Test", trial_days=15
            )

            # Should return False when Resend not available
            assert result is False

    @pytest.mark.asyncio
    async def test_welcome_email_html_structure(self, email_service):
        """Test welcome email has proper HTML structure"""
        with patch("resend.Emails.send") as mock_send:
            mock_send.return_value = {"id": "email_test"}

            await email_service.send_welcome_email(
                to="test@example.com", user_name="Test User", trial_days=15
            )

            call_args = mock_send.call_args[0][0]
            html = call_args["html"]

            # Check for essential HTML elements
            assert "<!DOCTYPE html>" in html
            assert "<html>" in html
            assert "<body" in html
            assert "</body>" in html
            assert "</html>" in html

            # Check for responsive meta tag
            assert "viewport" in html

    @pytest.mark.asyncio
    async def test_password_reset_token_expiry_warning(self, email_service):
        """Test password reset email includes expiry warning"""
        with patch("resend.Emails.send") as mock_send:
            mock_send.return_value = {"id": "email_test"}

            await email_service.send_password_reset_email(
                to="test@example.com", token="test123", user_name="Test"
            )

            call_args = mock_send.call_args[0][0]
            html = call_args["html"]

            # Should mention 1 hour expiry
            assert "1 hora" in html or "1h" in html
            assert "expira" in html.lower()
