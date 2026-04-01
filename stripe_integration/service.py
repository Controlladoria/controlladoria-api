"""
Stripe service
Business logic for subscription management
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import settings
from database import Plan, Subscription, SubscriptionStatus, User
from plan_features import get_plan_by_slug, get_plan_by_stripe_price_id, get_default_plan

from .client import StripeClient

logger = logging.getLogger(__name__)


def get_plan_from_price_id(db: Session, price_id: str) -> Optional[Plan]:
    """
    Map a Stripe price ID to a Plan record.

    First checks the Plan.stripe_price_id column in DB.
    Falls back to config-based slug mapping for plans without stripe_price_id set.
    """
    # Try DB lookup first (Plan.stripe_price_id column)
    plan = get_plan_by_stripe_price_id(db, price_id)
    if plan:
        return plan

    # Fallback: config-based mapping (slug derived from env settings)
    slug_map = {}
    if settings.stripe_price_id_basic:
        slug_map[settings.stripe_price_id_basic] = "basic"
    if settings.stripe_price_id:
        slug_map[settings.stripe_price_id] = "basic"  # Legacy
    if settings.stripe_price_id_pro:
        slug_map[settings.stripe_price_id_pro] = "pro"
    if settings.stripe_price_id_max:
        slug_map[settings.stripe_price_id_max] = "max"

    slug = slug_map.get(price_id)
    if slug:
        plan = get_plan_by_slug(db, slug)
        if plan:
            return plan

    # Price ID not recognized — don't silently default to basic.
    # Return None so the caller keeps the subscription's existing plan.
    logger.warning(f"No plan mapping found for price_id={price_id}. "
                   f"Set STRIPE_PRICE_ID_BASIC/PRO/MAX env vars or update plans.stripe_price_id in DB.")
    return None


class StripeService:
    """Service for managing Stripe subscriptions"""

    @staticmethod
    def create_checkout_session(user: User, db: Session, plan_slug: str = "basic") -> dict:
        """
        Create a Stripe Checkout session for user subscription

        If user doesn't have a Stripe customer, creates one.
        Returns checkout session URL.

        Args:
            user: User object
            db: Database session
            plan_slug: Plan slug (e.g., "basic", "pro", "max")
        """
        try:
            # Look up plan from DB
            plan = get_plan_by_slug(db, plan_slug)
            if not plan:
                raise HTTPException(
                    status_code=400,
                    detail=f"Plano '{plan_slug}' não encontrado."
                )

            # Determine Stripe price ID: Plan.stripe_price_id first, then config fallback
            price_id = plan.stripe_price_id
            if not price_id:
                config_map = {
                    "basic": settings.stripe_price_id_basic or settings.stripe_price_id,
                    "pro": settings.stripe_price_id_pro,
                    "max": settings.stripe_price_id_max,
                }
                price_id = config_map.get(plan_slug)

            if not price_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Nenhum preço configurado para o plano '{plan.display_name}'. Contate o suporte."
                )

            # Get or create subscription record for current org
            org_id = user.active_org_id
            subscription = (
                db.query(Subscription)
                .filter(Subscription.user_id == user.id, Subscription.organization_id == org_id)
                .first()
            )

            if not subscription:
                # No subscription record at all — create customer + subscription
                stripe_customer = StripeClient.create_customer(
                    email=user.email,
                    name=user.full_name or user.email,
                    metadata={"user_id": str(user.id), "plan_slug": plan_slug},
                )

                subscription = Subscription(
                    user_id=user.id,
                    organization_id=org_id,
                    stripe_customer_id=stripe_customer.id,
                    status=SubscriptionStatus.INCOMPLETE,
                    plan_id=plan.id,
                    max_users=plan.max_users,
                )
                db.add(subscription)
                db.commit()
                db.refresh(subscription)
            else:
                # Subscription exists — ensure we have a Stripe customer
                if not subscription.stripe_customer_id:
                    stripe_customer = StripeClient.create_customer(
                        email=user.email,
                        name=user.full_name or user.email,
                        metadata={"user_id": str(user.id), "plan_slug": plan_slug},
                    )
                    subscription.stripe_customer_id = stripe_customer.id

                subscription.plan_id = plan.id
                subscription.max_users = plan.max_users
                db.commit()

            # Create checkout session
            checkout_session = StripeClient.create_checkout_session(
                customer_id=subscription.stripe_customer_id,
                price_id=price_id,
                success_url=settings.stripe_success_url,
                cancel_url=settings.stripe_cancel_url,
                trial_days=settings.stripe_trial_days,
            )

            return {
                "checkout_url": checkout_session.url,
                "session_id": checkout_session.id,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Checkout session creation failed: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to create checkout session"
            )

    @staticmethod
    def create_portal_session(user: User, db: Session) -> dict:
        """Create a Stripe Customer Portal session"""
        try:
            subscription = (
                db.query(Subscription)
                .filter(Subscription.user_id == user.id, Subscription.organization_id == user.active_org_id)
                .first()
            )

            if not subscription:
                raise HTTPException(status_code=404, detail="Nenhuma assinatura encontrada")

            if not subscription.stripe_customer_id:
                raise HTTPException(
                    status_code=400,
                    detail="Você está no período de teste gratuito. Escolha um plano para acessar o portal de pagamento."
                )

            portal_session = StripeClient.create_portal_session(
                customer_id=subscription.stripe_customer_id,
                return_url=settings.frontend_url + "/account/subscription",
            )

            return {"portal_url": portal_session.url}

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Portal session creation failed: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to create portal session"
            )

    @staticmethod
    def get_subscription_status(user: User, db: Session) -> dict:
        """Get user's subscription status - queries Stripe directly for real-time data"""
        from datetime import datetime, timedelta

        subscription = (
            db.query(Subscription)
            .filter(Subscription.user_id == user.id, Subscription.organization_id == user.active_org_id)
            .first()
        )

        # Helper to build plan info for response
        def _plan_info(plan):
            if plan:
                return {
                    "plan_tier": plan.slug,
                    "plan_name": plan.display_name,
                    "max_users": plan.max_users,
                    "features": plan.features or {},
                }
            # Fallback when no plan record exists
            default = get_default_plan(db)
            if default:
                return {
                    "plan_tier": default.slug,
                    "plan_name": default.display_name,
                    "max_users": default.max_users,
                    "features": default.features or {},
                }
            return {
                "plan_tier": "basic",
                "plan_name": "Básico",
                "max_users": 1,
                "features": {},
            }

        # If no local subscription record at all, user is on free trial
        if not subscription:
            trial_end = user.created_at + timedelta(days=15)
            plan_data = _plan_info(None)
            return {
                "has_subscription": True,
                "status": "trialing",
                "trial_end": trial_end.isoformat(),
                "current_period_end": trial_end.isoformat(),
                "cancel_at_period_end": False,
                **plan_data,
            }

        # If subscription exists but no Stripe customer yet (local trial)
        if not subscription.stripe_customer_id:
            trial_end_dt = subscription.trial_end or (user.created_at + timedelta(days=15))
            is_trial_active = trial_end_dt > datetime.utcnow()
            plan_data = _plan_info(subscription.plan)
            return {
                "has_subscription": True,
                "status": "trialing" if is_trial_active else "expired",
                "trial_end": trial_end_dt.isoformat(),
                "current_period_end": trial_end_dt.isoformat(),
                "cancel_at_period_end": False,
                **plan_data,
            }

        # Query Stripe for real-time subscription data
        try:
            stripe_subscriptions = StripeClient.list_customer_subscriptions(
                subscription.stripe_customer_id
            )

            # Get the first active or trialing subscription
            active_stripe_sub = None
            for sub in stripe_subscriptions.data:
                if sub.status in ["active", "trialing"]:
                    active_stripe_sub = sub
                    break

            if active_stripe_sub:
                # Derive plan from Stripe's actual price ID
                stripe_price_id = None
                if active_stripe_sub.items and active_stripe_sub.items.data:
                    stripe_price_id = active_stripe_sub.items.data[0].price.id
                    plan = get_plan_from_price_id(db, stripe_price_id)
                    if plan:
                        subscription.plan_id = plan.id
                        subscription.max_users = plan.max_users
                    subscription.stripe_price_id = stripe_price_id

                # Sync local DB with Stripe data
                subscription.stripe_subscription_id = active_stripe_sub.id
                subscription.status = SubscriptionStatus(active_stripe_sub.status)
                subscription.trial_start = (
                    datetime.fromtimestamp(active_stripe_sub.trial_start)
                    if active_stripe_sub.trial_start
                    else None
                )
                subscription.trial_end = (
                    datetime.fromtimestamp(active_stripe_sub.trial_end)
                    if active_stripe_sub.trial_end
                    else None
                )
                subscription.current_period_start = (
                    datetime.fromtimestamp(active_stripe_sub.current_period_start)
                    if getattr(active_stripe_sub, 'current_period_start', None)
                    else None
                )
                subscription.current_period_end = (
                    datetime.fromtimestamp(active_stripe_sub.current_period_end)
                    if getattr(active_stripe_sub, 'current_period_end', None)
                    else None
                )
                subscription.cancel_at_period_end = active_stripe_sub.cancel_at_period_end
                db.commit()

                plan_data = _plan_info(subscription.plan)
                plan_name = plan_data["plan_name"]
                if active_stripe_sub.status == "trialing":
                    plan_name = f"{plan_name} (Teste)"

                return {
                    "has_subscription": True,
                    "status": active_stripe_sub.status,
                    "trial_end": (
                        datetime.fromtimestamp(active_stripe_sub.trial_end).isoformat()
                        if active_stripe_sub.trial_end
                        else None
                    ),
                    "current_period_end": (
                        datetime.fromtimestamp(active_stripe_sub.current_period_end).isoformat()
                        if getattr(active_stripe_sub, 'current_period_end', None)
                        else None
                    ),
                    "cancel_at_period_end": active_stripe_sub.cancel_at_period_end,
                    "plan_tier": plan_data["plan_tier"],
                    "plan_name": plan_name,
                    "max_users": plan_data["max_users"],
                    "features": plan_data["features"],
                }

        except Exception as e:
            logger.warning(f"Failed to query Stripe for subscription: {e}")
            # Fall back to local DB data if Stripe query fails

        # Return local DB data as fallback
        plan_data = _plan_info(subscription.plan)
        return {
            "has_subscription": True,
            "status": subscription.status.value,
            "trial_end": (
                subscription.trial_end.isoformat() if subscription.trial_end else None
            ),
            "current_period_end": (
                subscription.current_period_end.isoformat()
                if subscription.current_period_end
                else None
            ),
            "cancel_at_period_end": subscription.cancel_at_period_end,
            **plan_data,
        }

    @staticmethod
    def cancel_subscription(user: User, db: Session, immediate: bool = False) -> dict:
        """Cancel user's subscription"""
        try:
            subscription = (
                db.query(Subscription)
                .filter(Subscription.user_id == user.id, Subscription.organization_id == user.active_org_id)
                .first()
            )

            if not subscription or not subscription.stripe_subscription_id:
                raise HTTPException(
                    status_code=404, detail="No active subscription found"
                )

            # Cancel in Stripe
            stripe_sub = StripeClient.cancel_subscription(
                subscription.stripe_subscription_id, at_period_end=not immediate
            )

            # Update local record
            if immediate:
                subscription.status = SubscriptionStatus.CANCELED
                subscription.canceled_at = datetime.utcnow()
            else:
                subscription.cancel_at_period_end = True

            db.commit()

            return {
                "message": "Subscription canceled successfully",
                "canceled_at_period_end": not immediate,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Subscription cancellation failed: {e}")
            raise HTTPException(status_code=500, detail="Failed to cancel subscription")
