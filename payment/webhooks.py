"""
Asaas webhook event handlers.

Asaas sends POST requests with JSON payloads.
Auth: webhook access token configured in Asaas dashboard.
Events: https://docs.asaas.com/docs/webhooks
"""

import logging

from sqlalchemy.orm import Session

from config import now_brazil
from database import Subscription, SubscriptionStatus

logger = logging.getLogger(__name__)


def handle_webhook_event(event: dict, db: Session) -> dict:
    """
    Process an Asaas webhook event.
    Returns {status: "success"} or raises.
    """
    event_type = event.get("event")
    payment = event.get("payment", {})
    subscription_id = payment.get("subscription") or event.get("subscription", {}).get("id")

    logger.info(f"Asaas webhook: {event_type} (subscription: {subscription_id})")

    if not event_type:
        return {"status": "ignored", "reason": "no event type"}

    # Payment events
    if event_type == "PAYMENT_RECEIVED":
        _handle_payment_received(subscription_id, payment, db)
    elif event_type == "PAYMENT_CONFIRMED":
        _handle_payment_received(subscription_id, payment, db)
    elif event_type == "PAYMENT_OVERDUE":
        _handle_payment_overdue(subscription_id, payment, db)
    elif event_type == "PAYMENT_DELETED":
        _handle_payment_deleted(subscription_id, payment, db)
    elif event_type == "PAYMENT_REFUNDED":
        _handle_payment_refunded(subscription_id, payment, db)

    # Subscription events
    elif event_type == "SUBSCRIPTION_DELETED":
        _handle_subscription_deleted(subscription_id, db)
    elif event_type == "SUBSCRIPTION_UPDATED":
        _handle_subscription_updated(subscription_id, event.get("subscription", {}), db)

    else:
        logger.debug(f"Asaas webhook: unhandled event type '{event_type}'")

    return {"status": "success"}


def _find_subscription(subscription_id: str, db: Session):
    """Find local subscription by Asaas subscription ID."""
    if not subscription_id:
        return None
    return (
        db.query(Subscription)
        .filter(Subscription.payment_subscription_id == subscription_id)
        .first()
    )


def _handle_payment_received(subscription_id: str, payment: dict, db: Session):
    """Payment was successfully received — activate subscription."""
    sub = _find_subscription(subscription_id, db)
    if not sub:
        logger.warning(f"Payment received for unknown subscription: {subscription_id}")
        return

    if sub.status != SubscriptionStatus.ACTIVE:
        logger.info(f"Subscription {subscription_id} activated (was {sub.status})")
        sub.status = SubscriptionStatus.ACTIVE

    # Update period from payment due date
    due_date = payment.get("dueDate")
    if due_date:
        try:
            from datetime import datetime
            sub.current_period_start = datetime.fromisoformat(due_date)
            # Next period = due_date + 1 month (approximate)
            from dateutil.relativedelta import relativedelta
            sub.current_period_end = sub.current_period_start + relativedelta(months=1)
        except Exception:
            pass

    db.commit()


def _handle_payment_overdue(subscription_id: str, payment: dict, db: Session):
    """Payment is overdue — mark subscription as past_due."""
    sub = _find_subscription(subscription_id, db)
    if not sub:
        return

    logger.info(f"Subscription {subscription_id} past due")
    sub.status = SubscriptionStatus.PAST_DUE
    db.commit()


def _handle_payment_deleted(subscription_id: str, payment: dict, db: Session):
    """Payment was deleted — check if subscription is still valid."""
    sub = _find_subscription(subscription_id, db)
    if not sub:
        return
    # Don't change status here — deletion of a single payment
    # doesn't necessarily mean the subscription is dead
    logger.info(f"Payment deleted for subscription {subscription_id}")


def _handle_payment_refunded(subscription_id: str, payment: dict, db: Session):
    """Payment was refunded."""
    sub = _find_subscription(subscription_id, db)
    if not sub:
        return
    logger.info(f"Payment refunded for subscription {subscription_id}")


def _handle_subscription_deleted(subscription_id: str, db: Session):
    """Subscription was canceled/deleted in Asaas."""
    sub = _find_subscription(subscription_id, db)
    if not sub:
        return

    logger.info(f"Subscription {subscription_id} deleted/canceled")
    sub.status = SubscriptionStatus.CANCELED
    sub.canceled_at = now_brazil()
    db.commit()


def _handle_subscription_updated(subscription_id: str, asaas_sub: dict, db: Session):
    """Subscription was updated in Asaas (plan change, etc.)."""
    sub = _find_subscription(subscription_id, db)
    if not sub:
        return

    logger.info(f"Subscription {subscription_id} updated")
    # Sync value if changed (plan upgrade/downgrade)
    new_value = asaas_sub.get("value")
    if new_value:
        # Try to find matching plan
        from database import Plan
        plan = (
            db.query(Plan)
            .filter(Plan.price_monthly_brl == new_value, Plan.is_active == True)
            .first()
        )
        if plan and plan.id != sub.plan_id:
            logger.info(f"Plan changed to {plan.slug} (value={new_value})")
            sub.plan_id = plan.id
            sub.max_users = plan.max_users

    db.commit()
