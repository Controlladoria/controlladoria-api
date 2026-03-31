"""
Unit tests for Billing Router

Tests Stripe integration endpoints:
- Create checkout session
- Create customer portal session
- Get subscription status
- Cancel subscription
- Webhook handling
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from database import User
from api import app

client = TestClient(app)


class TestCreateCheckoutSession:
    """Test creating Stripe checkout session"""

    @patch("routers.billing.get_current_active_user")
    @patch("routers.billing.StripeService.create_checkout_session")
    def test_create_checkout_1_member(
        self, mock_create_session, mock_current_user
    ):
        """Test creating checkout for 1-member plan"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_create_session.return_value = {
            "checkout_url": "https://checkout.stripe.com/session_123"
        }

        response = client.post("/stripe/create-checkout-session?members=1")

        assert response.status_code == 200
        data = response.json()
        assert "checkout_url" in data

    @patch("routers.billing.get_current_active_user")
    @patch("routers.billing.StripeService.create_checkout_session")
    def test_create_checkout_3_members(
        self, mock_create_session, mock_current_user
    ):
        """Test creating checkout for 3-member plan"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_create_session.return_value = {
            "checkout_url": "https://checkout.stripe.com/session_456"
        }

        response = client.post("/stripe/create-checkout-session?members=3")

        assert response.status_code == 200

    @patch("routers.billing.get_current_active_user")
    def test_create_checkout_invalid_members(self, mock_current_user):
        """Test creating checkout with invalid member count"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        # Only 1, 3, or 5 members allowed
        response = client.post("/stripe/create-checkout-session?members=10")

        assert response.status_code == 400

    @patch("routers.billing.get_current_active_user")
    @patch("routers.billing.StripeService.create_checkout_session")
    def test_create_checkout_stripe_error(
        self, mock_create_session, mock_current_user
    ):
        """Test handling Stripe errors during checkout"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_create_session.side_effect = Exception("Stripe API error")

        response = client.post("/stripe/create-checkout-session?members=1")

        assert response.status_code == 500


class TestCreatePortalSession:
    """Test creating Stripe customer portal session"""

    @patch("routers.billing.get_current_active_user")
    @patch("routers.billing.StripeService.create_portal_session")
    def test_create_portal_session(
        self, mock_create_portal, mock_current_user
    ):
        """Test creating customer portal session"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_create_portal.return_value = {
            "portal_url": "https://billing.stripe.com/session_789"
        }

        response = client.post("/stripe/create-portal-session")

        assert response.status_code == 200
        data = response.json()
        assert "portal_url" in data

    @patch("routers.billing.get_current_active_user")
    @patch("routers.billing.StripeService.create_portal_session")
    def test_create_portal_no_subscription(
        self, mock_create_portal, mock_current_user
    ):
        """Test creating portal when user has no subscription"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_create_portal.side_effect = HTTPException(
            status_code=400, detail="No subscription found"
        )

        response = client.post("/stripe/create-portal-session")

        assert response.status_code == 400


class TestGetSubscriptionStatus:
    """Test getting subscription status"""

    @patch("routers.billing.get_current_active_user")
    @patch("routers.billing.StripeService.get_subscription_status")
    def test_get_status_active(self, mock_get_status, mock_current_user):
        """Test getting active subscription status"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_get_status.return_value = {
            "status": "active",
            "current_period_end": "2026-03-01",
            "cancel_at_period_end": False,
        }

        response = client.get("/stripe/subscription-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"

    @patch("routers.billing.get_current_active_user")
    @patch("routers.billing.StripeService.get_subscription_status")
    def test_get_status_trialing(self, mock_get_status, mock_current_user):
        """Test getting trialing subscription status"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_get_status.return_value = {
            "status": "trialing",
            "trial_end": "2026-02-15",
        }

        response = client.get("/stripe/subscription-status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "trialing"


class TestCancelSubscription:
    """Test canceling subscription"""

    @patch("routers.billing.get_current_active_user")
    @patch("routers.billing.StripeService.cancel_subscription")
    def test_cancel_at_period_end(self, mock_cancel, mock_current_user):
        """Test canceling subscription at period end"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_cancel.return_value = {
            "message": "Subscription will cancel at period end"
        }

        response = client.post("/stripe/cancel-subscription?immediate=false")

        assert response.status_code == 200
        data = response.json()
        assert "cancel" in data["message"].lower()

    @patch("routers.billing.get_current_active_user")
    @patch("routers.billing.StripeService.cancel_subscription")
    def test_cancel_immediately(self, mock_cancel, mock_current_user):
        """Test immediate subscription cancellation"""
        mock_user = MagicMock(spec=User)
        mock_user.id = 1
        mock_current_user.return_value = mock_user

        mock_cancel.return_value = {"message": "Subscription canceled immediately"}

        response = client.post("/stripe/cancel-subscription?immediate=true")

        assert response.status_code == 200


class TestStripeWebhook:
    """Test Stripe webhook handling"""

    @patch("routers.billing.get_db")
    @patch("routers.billing.StripeClient.construct_webhook_event")
    @patch("routers.billing.handle_webhook_event")
    def test_webhook_valid_signature(
        self, mock_handle, mock_construct, mock_db
    ):
        """Test webhook with valid signature"""
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        mock_event = {
            "type": "checkout.session.completed",
            "data": {"object": {}},
        }
        mock_construct.return_value = mock_event

        response = client.post(
            "/stripe/webhook",
            headers={"stripe-signature": "valid_sig_123"},
            content=b'{"type":"checkout.session.completed"}',
        )

        assert response.status_code == 200
        assert response.json()["status"] == "success"
        mock_handle.assert_called_once_with(mock_event, mock_db_session)

    @patch("routers.billing.get_db")
    @patch("routers.billing.StripeClient.construct_webhook_event")
    def test_webhook_invalid_signature(self, mock_construct, mock_db):
        """Test webhook with invalid signature"""
        mock_construct.side_effect = ValueError("Invalid signature")

        response = client.post(
            "/stripe/webhook",
            headers={"stripe-signature": "invalid_sig"},
            content=b'{"type":"test"}',
        )

        assert response.status_code == 400

    @patch("routers.billing.get_db")
    @patch("routers.billing.StripeClient.construct_webhook_event")
    @patch("routers.billing.handle_webhook_event")
    def test_webhook_processing_error(
        self, mock_handle, mock_construct, mock_db
    ):
        """Test webhook processing error"""
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        mock_event = {"type": "test.event"}
        mock_construct.return_value = mock_event
        mock_handle.side_effect = Exception("Processing failed")

        response = client.post(
            "/stripe/webhook",
            headers={"stripe-signature": "sig"},
            content=b'{"type":"test"}',
        )

        assert response.status_code == 400
