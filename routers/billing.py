"""
Billing Router — Asaas payment integration.
Handles subscriptions, checkout, billing history, plan changes, and webhooks.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from config import settings
from database import Plan, User, get_db
from payment.service import (
    cancel_subscription,
    change_plan,
    create_checkout,
    get_billing_history,
    get_subscription_status,
)
from payment.webhooks import handle_webhook_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/plans")
async def list_plans(db: Session = Depends(get_db)):
    """List all active plans for pricing page (public endpoint)."""
    plans = (
        db.query(Plan)
        .filter(Plan.is_active == True)
        .order_by(Plan.sort_order)
        .all()
    )
    return [
        {
            "slug": p.slug,
            "display_name": p.display_name,
            "description": p.description,
            "max_users": p.max_users,
            "price_monthly_brl": float(p.price_monthly_brl) if p.price_monthly_brl else None,
            "features": p.features or {},
            "is_highlighted": p.is_highlighted,
            "sort_order": p.sort_order,
        }
        for p in plans
    ]


@router.post("/create-checkout")
async def create_checkout_session(
    plan: str = Query("basic", description="Plan slug: basic, pro, max"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create a checkout session for a plan. Returns a payment URL."""
    try:
        result = create_checkout(current_user, db, plan_slug=plan)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/subscription-status")
async def subscription_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get current subscription status."""
    return get_subscription_status(current_user, db)


@router.post("/cancel")
async def cancel(
    immediate: bool = Query(False, description="Cancel immediately vs at period end"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Cancel the current subscription."""
    try:
        return cancel_subscription(current_user, db, immediate=immediate)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history")
async def billing_history(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get payment history for subscription management page."""
    return get_billing_history(current_user, db)


@router.post("/change-plan")
async def change_subscription_plan(
    plan: str = Query(..., description="New plan slug: basic, pro, max"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Upgrade or downgrade subscription plan."""
    try:
        return change_plan(current_user, db, new_plan_slug=plan)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Asaas webhook events."""
    # Verify webhook token
    token = request.headers.get("asaas-access-token") or request.query_params.get("access_token")
    if settings.asaas_webhook_token and token != settings.asaas_webhook_token:
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    try:
        payload = await request.json()
        result = handle_webhook_event(payload, db)
        return result
    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        raise HTTPException(status_code=500, detail="Webhook processing failed")


# ── Legacy Stripe endpoints (redirect to new paths) ──────────

legacy_router = APIRouter(prefix="/stripe", tags=["Billing (Legacy)"])


@legacy_router.get("/plans")
async def legacy_plans(db: Session = Depends(get_db)):
    return await list_plans(db)


@legacy_router.post("/create-checkout-session")
async def legacy_checkout(
    plan: str = Query("basic"),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return await create_checkout_session(plan, current_user, db)


@legacy_router.get("/subscription-status")
async def legacy_status(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return await subscription_status(current_user, db)


@legacy_router.post("/cancel-subscription")
async def legacy_cancel(
    immediate: bool = Query(False),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return await cancel(immediate, current_user, db)


@legacy_router.post("/webhook")
async def legacy_webhook(request: Request, db: Session = Depends(get_db)):
    return await webhook(request, db)
