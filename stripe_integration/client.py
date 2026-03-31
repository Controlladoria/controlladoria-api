"""
Stripe API client wrapper
"""

import stripe

from config import settings

# Initialize Stripe
stripe.api_key = settings.stripe_api_key


class StripeClient:
    """Wrapper for Stripe API operations"""

    @staticmethod
    def create_customer(email: str, name: str = None, metadata: dict = None):
        """Create a Stripe customer"""
        return stripe.Customer.create(email=email, name=name, metadata=metadata or {})

    @staticmethod
    def create_checkout_session(
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        trial_days: int = None,
    ):
        """Create a Stripe Checkout session for subscription"""
        session_params = {
            "customer": customer_id,
            "line_items": [
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            "mode": "subscription",
            "success_url": success_url,
            "cancel_url": cancel_url,
        }

        if trial_days:
            session_params["subscription_data"] = {"trial_period_days": trial_days}

        return stripe.checkout.Session.create(**session_params)

    @staticmethod
    def create_portal_session(customer_id: str, return_url: str):
        """Create a Stripe Customer Portal session"""
        return stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )

    @staticmethod
    def get_subscription(subscription_id: str):
        """Retrieve a subscription"""
        return stripe.Subscription.retrieve(subscription_id)

    @staticmethod
    def list_customer_subscriptions(customer_id: str):
        """List all subscriptions for a customer"""
        return stripe.Subscription.list(customer=customer_id, limit=10)

    @staticmethod
    def cancel_subscription(subscription_id: str, at_period_end: bool = True):
        """Cancel a subscription"""
        if at_period_end:
            return stripe.Subscription.modify(
                subscription_id, cancel_at_period_end=True
            )
        else:
            return stripe.Subscription.delete(subscription_id)

    @staticmethod
    def construct_webhook_event(payload: bytes, sig_header: str, webhook_secret: str):
        """Construct and verify webhook event"""
        return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
