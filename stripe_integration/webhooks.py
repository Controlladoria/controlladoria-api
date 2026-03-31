"""
Stripe webhook handlers
Processes Stripe events to keep subscription status synchronized
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from database import Subscription, SubscriptionStatus
from .service import get_plan_from_price_id

logger = logging.getLogger(__name__)


def handle_webhook_event(event: dict, db: Session):
    """
    Handle Stripe webhook events

    Args:
        event: Stripe event dictionary
        db: Database session
    """
    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"Processing Stripe webhook: {event_type}")

    # Handle checkout completion
    if event_type == "checkout.session.completed":
        handle_checkout_completed(data, db)

    # Handle subscription creation
    elif event_type == "customer.subscription.created":
        handle_subscription_created(data, db)

    # Handle subscription updates
    elif event_type == "customer.subscription.updated":
        handle_subscription_updated(data, db)

    # Handle subscription deletion
    elif event_type == "customer.subscription.deleted":
        handle_subscription_deleted(data, db)

    # Handle successful payment
    elif event_type == "invoice.payment_succeeded":
        handle_payment_succeeded(data, db)

    # Handle failed payment
    elif event_type == "invoice.payment_failed":
        handle_payment_failed(data, db)

    else:
        logger.info(f"Unhandled event type: {event_type}")


def handle_checkout_completed(session: dict, db: Session):
    """Handle checkout.session.completed event"""
    try:
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")

        subscription = (
            db.query(Subscription)
            .filter(Subscription.stripe_customer_id == customer_id)
            .first()
        )

        if subscription:
            subscription.stripe_subscription_id = subscription_id
            subscription.status = (
                SubscriptionStatus.TRIALING
                if session.get("mode") == "subscription"
                else SubscriptionStatus.ACTIVE
            )
            db.commit()
            logger.info(f"Checkout completed for customer {customer_id}")

    except Exception as e:
        logger.error(f"Error handling checkout completed: {e}")
        db.rollback()


def _sync_plan_from_stripe(subscription: Subscription, sub: dict, db: Session):
    """Sync plan_id and max_users from Stripe's price ID"""
    items = sub.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id", "")
        if price_id:
            plan = get_plan_from_price_id(db, price_id)
            if plan:
                old_plan_slug = subscription.plan.slug if subscription.plan else None
                if plan.slug != old_plan_slug:
                    logger.info(
                        f"Plan changed: {old_plan_slug} -> {plan.slug}"
                    )
                subscription.plan_id = plan.id
                subscription.max_users = plan.max_users
            subscription.stripe_price_id = price_id


def handle_subscription_created(sub: dict, db: Session):
    """Handle customer.subscription.created event"""
    try:
        subscription = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == sub["id"])
            .first()
        )

        if subscription:
            subscription.status = SubscriptionStatus(sub["status"])
            subscription.trial_start = (
                datetime.fromtimestamp(sub["trial_start"])
                if sub.get("trial_start")
                else None
            )
            subscription.trial_end = (
                datetime.fromtimestamp(sub["trial_end"])
                if sub.get("trial_end")
                else None
            )
            subscription.current_period_start = datetime.fromtimestamp(
                sub["current_period_start"]
            )
            subscription.current_period_end = datetime.fromtimestamp(
                sub["current_period_end"]
            )

            # Sync plan from Stripe price ID
            _sync_plan_from_stripe(subscription, sub, db)

            db.commit()
            plan_slug = subscription.plan.slug if subscription.plan else "unknown"
            logger.info(f"Subscription created: {sub['id']}, plan: {plan_slug}, max_users: {subscription.max_users}")

    except Exception as e:
        logger.error(f"Error handling subscription created: {e}")
        db.rollback()


def handle_subscription_updated(sub: dict, db: Session):
    """Handle customer.subscription.updated event"""
    try:
        subscription = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == sub["id"])
            .first()
        )

        if subscription:
            subscription.status = SubscriptionStatus(sub["status"])
            subscription.cancel_at_period_end = sub.get("cancel_at_period_end", False)
            subscription.current_period_start = datetime.fromtimestamp(
                sub["current_period_start"]
            )
            subscription.current_period_end = datetime.fromtimestamp(
                sub["current_period_end"]
            )

            # Sync plan from Stripe price ID (handles plan changes)
            _sync_plan_from_stripe(subscription, sub, db)

            db.commit()
            logger.info(f"Subscription updated: {sub['id']}, status: {sub['status']}")

    except Exception as e:
        logger.error(f"Error handling subscription updated: {e}")
        db.rollback()


def handle_subscription_deleted(sub: dict, db: Session):
    """Handle customer.subscription.deleted event"""
    try:
        subscription = (
            db.query(Subscription)
            .filter(Subscription.stripe_subscription_id == sub["id"])
            .first()
        )

        if subscription:
            subscription.status = SubscriptionStatus.CANCELED
            subscription.canceled_at = datetime.utcnow()
            db.commit()
            logger.info(f"Subscription deleted: {sub['id']}")

    except Exception as e:
        logger.error(f"Error handling subscription deleted: {e}")
        db.rollback()


def handle_payment_succeeded(invoice: dict, db: Session):
    """Handle invoice.payment_succeeded event"""
    try:
        subscription_id = invoice.get("subscription")
        if subscription_id:
            subscription = (
                db.query(Subscription)
                .filter(Subscription.stripe_subscription_id == subscription_id)
                .first()
            )

            if subscription and subscription.status != SubscriptionStatus.ACTIVE:
                subscription.status = SubscriptionStatus.ACTIVE
                db.commit()
                logger.info(f"Payment succeeded for subscription: {subscription_id}")

    except Exception as e:
        logger.error(f"Error handling payment succeeded: {e}")
        db.rollback()


def handle_payment_failed(invoice: dict, db: Session):
    """Handle invoice.payment_failed event"""
    try:
        subscription_id = invoice.get("subscription")
        if subscription_id:
            subscription = (
                db.query(Subscription)
                .filter(Subscription.stripe_subscription_id == subscription_id)
                .first()
            )

            if subscription:
                subscription.status = SubscriptionStatus.PAST_DUE
                db.commit()
                logger.warning(f"Payment failed for subscription: {subscription_id}")

    except Exception as e:
        logger.error(f"Error handling payment failed: {e}")
        db.rollback()
