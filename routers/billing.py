"""
Billing Router
Handles Stripe subscription and billing endpoints:
- Create checkout session
- Manage customer portal
- Get subscription status
- Cancel subscription
- Stripe webhooks
- List available plans
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from config import settings
from database import User, get_db
from stripe_integration import StripeClient, StripeService, handle_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stripe", tags=["Billing"])


@router.get("/plans")
async def list_plans(db: Session = Depends(get_db)):
    """
    List all active plans for pricing page (public endpoint)

    Returns plan details including features, pricing, and display information.
    """
    from plan_features import get_active_plans
    plans = get_active_plans(db)
    return [
        {
            "slug": p.slug,
            "display_name": p.display_name,
            "description": p.description,
            "max_users": p.max_users,
            "price_monthly_brl": p.price_monthly_brl,
            "features": p.features or {},
            "is_highlighted": p.is_highlighted,
            "sort_order": p.sort_order,
        }
        for p in plans
    ]


@router.post("/create-checkout-session")
async def create_checkout_session(
    plan: str = Query("basic", description="Plan slug (e.g., basic, pro, max)"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Create Stripe Checkout session for subscription

    Starts the subscription flow with a 15-day free trial.
    Returns checkout URL to redirect user to Stripe.

    Args:
        plan: Plan slug (e.g., "basic", "pro", "max")
    """
    # Validate plan slug exists in DB
    from plan_features import get_plan_by_slug
    plan_record = get_plan_by_slug(db, plan)
    if not plan_record:
        raise HTTPException(status_code=400, detail=f"Plano '{plan}' não encontrado.")

    try:
        result = StripeService.create_checkout_session(current_user, db, plan)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Checkout session error: {e}")
        raise HTTPException(status_code=500, detail="Falha ao criar sessão de checkout")


@router.post("/create-portal-session")
async def create_portal_session(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """
    Create Stripe Customer Portal session

    Allows users to manage their subscription, payment methods, and invoices.
    Returns portal URL to redirect user to Stripe.
    """
    try:
        result = StripeService.create_portal_session(current_user, db)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Portal session error: {e}")
        raise HTTPException(status_code=500, detail="Falha ao criar sessão do portal")


@router.get("/subscription-status")
async def get_subscription_status(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """
    Get current user's subscription status

    Returns subscription details including trial status, period end, plan info, and features.
    """
    try:
        status = StripeService.get_subscription_status(current_user, db)
        return status
    except Exception as e:
        logger.error(f"Subscription status error: {e}")
        raise HTTPException(status_code=500, detail="Falha ao obter status da assinatura")


@router.post("/cancel-subscription")
async def cancel_subscription(
    immediate: bool = False,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """
    Cancel user's subscription

    By default, cancels at period end. Set immediate=true to cancel immediately.
    """
    try:
        result = StripeService.cancel_subscription(current_user, db, immediate)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Subscription cancellation error: {e}")
        raise HTTPException(status_code=500, detail="Falha ao cancelar assinatura")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe webhook endpoint

    Handles Stripe events to keep subscription status synchronized.
    Events: checkout.session.completed, customer.subscription.*, invoice.payment_*
    """
    try:
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")

        # Verify webhook signature
        event = StripeClient.construct_webhook_event(
            payload, sig_header, settings.stripe_webhook_secret
        )

        # Handle the event
        handle_webhook_event(event, db)

        return {"status": "success"}

    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        raise HTTPException(status_code=400, detail="Payload inválido")
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=400, detail="Erro no webhook")
