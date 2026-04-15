"""
Payment service — business logic for Asaas subscriptions.
Same interface as the previous StripeService.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from config import now_brazil, settings
from database import (
    Organization,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
)
from payment.client import AsaasClient, AsaasError

logger = logging.getLogger(__name__)


def _get_asaas_client() -> AsaasClient:
    return AsaasClient()


def _get_org_id(user: User) -> Optional[int]:
    return (
        getattr(user, "_active_org_id", None)
        or getattr(user, "active_org_id", None)
    )


def _get_subscription(db: Session, user: User) -> Optional[Subscription]:
    """Get subscription for user's active organization (or user-level fallback)."""
    org_id = _get_org_id(user)
    if org_id:
        sub = (
            db.query(Subscription)
            .filter(
                Subscription.user_id == user.id,
                Subscription.organization_id == org_id,
            )
            .first()
        )
        if sub:
            return sub
    # Fallback: user-level subscription
    return (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id)
        .first()
    )


def _get_plan_by_slug(db: Session, slug: str) -> Optional[Plan]:
    return db.query(Plan).filter(Plan.slug == slug, Plan.is_active == True).first()


# ── Public API ─────────────────────────────────────────────────


def create_checkout(
    user: User, db: Session, plan_slug: str = "basic"
) -> dict:
    """
    Create checkout for a plan.
    Returns {checkout_url, subscription_id} where checkout_url is the
    Asaas hosted payment page for the first subscription charge.
    """
    plan = _get_plan_by_slug(db, plan_slug)
    if not plan:
        raise ValueError(f"Plan '{plan_slug}' not found")

    client = _get_asaas_client()
    org_id = _get_org_id(user)

    # Get or create local subscription record
    sub = _get_subscription(db, user)
    if not sub:
        sub = Subscription(
            user_id=user.id,
            organization_id=org_id,
            status=SubscriptionStatus.INCOMPLETE,
            plan_id=plan.id,
            max_users=plan.max_users,
        )
        db.add(sub)
        db.flush()

    # Create Asaas customer if needed
    if not sub.payment_customer_id:
        try:
            customer = client.create_customer(
                name=user.full_name or user.email,
                email=user.email,
                cpf_cnpj=getattr(user, "cnpj", None),
            )
            sub.payment_customer_id = customer["id"]
            db.flush()
        except AsaasError as e:
            raise ValueError(f"Failed to create payment customer: {e}")

    # Trial: first charge 15 days from now
    trial_days = settings.asaas_trial_days
    next_due = (now_brazil() + timedelta(days=trial_days)).strftime("%Y-%m-%d")

    # Create Asaas subscription
    try:
        asaas_sub = client.create_subscription(
            customer_id=sub.payment_customer_id,
            value=float(plan.price_monthly_brl),
            cycle="MONTHLY",
            billing_type="UNDEFINED",  # Customer picks PIX/boleto/card
            description=f"ControlladorIA — {plan.display_name}",
            next_due_date=next_due,
        )

        sub.payment_subscription_id = asaas_sub["id"]
        sub.status = SubscriptionStatus.TRIALING
        sub.plan_id = plan.id
        sub.max_users = plan.max_users
        sub.trial_start = now_brazil()
        sub.trial_end = now_brazil() + timedelta(days=trial_days)
        db.commit()

        # Get the first payment's invoice URL (checkout page)
        checkout_url = settings.asaas_success_url  # fallback
        try:
            payments = client.list_subscription_payments(asaas_sub["id"], limit=1)
            if payments.get("data"):
                first_payment = payments["data"][0]
                checkout_url = first_payment.get("invoiceUrl") or checkout_url
        except Exception:
            pass

        return {
            "checkout_url": checkout_url,
            "subscription_id": asaas_sub["id"],
        }

    except AsaasError as e:
        raise ValueError(f"Failed to create subscription: {e}")


def get_subscription_status(user: User, db: Session) -> dict:
    """
    Get current subscription status.
    Returns same format as previous Stripe integration for backward compat.
    """
    sub = _get_subscription(db, user)

    # No subscription record — implicit trial
    if not sub:
        trial_end = user.created_at + timedelta(days=settings.asaas_trial_days)
        is_trial_active = now_brazil() < trial_end
        return {
            "has_subscription": False,
            "status": "trialing" if is_trial_active else "expired",
            "trial_end": trial_end.isoformat(),
            "current_period_end": None,
            "cancel_at_period_end": False,
            "plan_tier": "basic",
            "plan_name": "Trial",
            "max_users": 1,
            "features": {},
        }

    # Has local subscription — try to sync with Asaas
    if sub.payment_subscription_id:
        try:
            client = _get_asaas_client()
            asaas_sub = client.get_subscription(sub.payment_subscription_id)
            _sync_subscription(sub, asaas_sub, db)
        except Exception as e:
            logger.warning(f"Failed to sync with Asaas: {e}, using local data")

    # Build response
    plan = db.query(Plan).filter(Plan.id == sub.plan_id).first() if sub.plan_id else None

    return {
        "has_subscription": True,
        "status": sub.status.value if sub.status else "trialing",
        "trial_end": sub.trial_end.isoformat() if sub.trial_end else None,
        "current_period_end": (
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        "cancel_at_period_end": sub.cancel_at_period_end or False,
        "plan_tier": plan.slug if plan else "basic",
        "plan_name": plan.display_name if plan else "Visão",
        "max_users": sub.max_users or 1,
        "features": plan.features if plan else {},
    }


def cancel_subscription(
    user: User, db: Session, immediate: bool = False
) -> dict:
    """Cancel the user's subscription."""
    sub = _get_subscription(db, user)
    if not sub or not sub.payment_subscription_id:
        raise ValueError("No active subscription to cancel")

    client = _get_asaas_client()

    try:
        client.cancel_subscription(sub.payment_subscription_id)
    except AsaasError as e:
        logger.warning(f"Asaas cancel failed (may already be canceled): {e}")

    sub.status = SubscriptionStatus.CANCELED
    sub.canceled_at = now_brazil()
    sub.cancel_at_period_end = not immediate
    db.commit()

    return {
        "message": "Assinatura cancelada com sucesso",
        "canceled_at_period_end": not immediate,
    }


def get_billing_history(user: User, db: Session) -> list:
    """Get payment history for the subscription management page."""
    sub = _get_subscription(db, user)
    if not sub or not sub.payment_customer_id:
        return []

    client = _get_asaas_client()

    try:
        result = client.list_customer_payments(sub.payment_customer_id, limit=50)
        payments = result.get("data", [])

        return [
            {
                "id": p["id"],
                "date": p.get("dateCreated"),
                "due_date": p.get("dueDate"),
                "value": p.get("value"),
                "net_value": p.get("netValue"),
                "status": p.get("status"),
                "billing_type": p.get("billingType"),
                "invoice_url": p.get("invoiceUrl"),
                "description": p.get("description", ""),
            }
            for p in payments
        ]
    except AsaasError as e:
        logger.warning(f"Failed to fetch billing history: {e}")
        return []


def change_plan(user: User, db: Session, new_plan_slug: str) -> dict:
    """Upgrade or downgrade the user's subscription plan."""
    sub = _get_subscription(db, user)
    if not sub or not sub.payment_subscription_id:
        raise ValueError("No active subscription to change")

    new_plan = _get_plan_by_slug(db, new_plan_slug)
    if not new_plan:
        raise ValueError(f"Plan '{new_plan_slug}' not found")

    client = _get_asaas_client()

    try:
        client.update_subscription(
            sub.payment_subscription_id,
            value=float(new_plan.price_monthly_brl),
            description=f"ControlladorIA — {new_plan.display_name}",
            updatePendingPayments=True,
        )

        sub.plan_id = new_plan.id
        sub.max_users = new_plan.max_users
        db.commit()

        return {
            "message": f"Plano alterado para {new_plan.display_name}",
            "plan": new_plan.slug,
            "price": float(new_plan.price_monthly_brl),
        }
    except AsaasError as e:
        raise ValueError(f"Failed to change plan: {e}")


# ── Internal helpers ───────────────────────────────────────────


def _sync_subscription(sub: Subscription, asaas_sub: dict, db: Session):
    """Sync local subscription record with Asaas data."""
    status_map = {
        "ACTIVE": SubscriptionStatus.ACTIVE,
        "INACTIVE": SubscriptionStatus.CANCELED,
        "EXPIRED": SubscriptionStatus.CANCELED,
    }
    asaas_status = asaas_sub.get("status", "")
    if asaas_status in status_map:
        sub.status = status_map[asaas_status]

    next_due = asaas_sub.get("nextDueDate")
    if next_due:
        try:
            sub.current_period_end = datetime.fromisoformat(next_due)
        except (ValueError, TypeError):
            pass

    db.flush()
