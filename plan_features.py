"""
Plan Features — Helper module for plan-based feature gating

Feature keys are just strings stored in the Plan.features JSON column.
This module provides constants for known feature keys and helper functions
to query plans from the database.

The Plan table is the single source of truth for all plan definitions.
Stakeholders can edit plan names, features, visibility, and seat limits
directly in the database without code changes.
"""

from typing import Optional, List

from sqlalchemy.orm import Session

# ─── FEATURE KEY CONSTANTS ─────────────────────────────────────────────────────
# These are referenced in code for feature gating.
# New features can be added to the Plan.features JSON anytime without migrations.

CASH_FLOW_DIRECT = "cash_flow_direct"
TEAM_MANAGEMENT = "team_management"
API_ACCESS = "api_access"
PRIORITY_SUPPORT = "priority_support"
WHITE_LABEL = "white_label"  # Max plan: custom org logo on exports
AI_ADVISOR = "ai_advisor"  # Pro/Max plans: AI financial advisor chat


# ─── HELPER FUNCTIONS ──────────────────────────────────────────────────────────

def get_default_plan(db: Session):
    """Get the default plan (used for trials)"""
    from database import Plan
    return db.query(Plan).filter(Plan.is_default == True).first()


def get_plan_by_slug(db: Session, slug: str):
    """Get a plan by its slug identifier"""
    from database import Plan
    return db.query(Plan).filter(Plan.slug == slug).first()


def get_plan_by_stripe_price_id(db: Session, price_id: str):
    """Get a plan by its Stripe price ID"""
    from database import Plan
    if not price_id:
        return None
    return db.query(Plan).filter(Plan.stripe_price_id == price_id).first()


def get_active_plans(db: Session) -> list:
    """Get all active (visible) plans ordered by sort_order"""
    from database import Plan
    return (
        db.query(Plan)
        .filter(Plan.is_active == True)
        .order_by(Plan.sort_order)
        .all()
    )


def has_plan_feature(plan, feature_key: str) -> bool:
    """
    Check if a plan has a specific feature (claims-based check).

    Args:
        plan: Plan object (or None)
        feature_key: Feature key string (e.g., "cash_flow_direct")

    Returns:
        True if the plan has the feature, False otherwise
    """
    if plan is None:
        return False
    features = getattr(plan, "features", None)
    if not features or not isinstance(features, dict):
        return False
    return features.get(feature_key, False)


def get_active_plan(db: Session, user):
    """
    Resolve the Plan backing a user's current subscription.

    Multi-org aware: prefers the active organization's subscription, falling
    back to the legacy user-level subscription, then to the default plan.

    Returns:
        Plan object, or None if nothing could be resolved.
    """
    from database import Subscription

    org_id = getattr(user, "_active_org_id", None) or getattr(user, "active_org_id", None)

    subscription = None
    if org_id:
        subscription = (
            db.query(Subscription)
            .filter(Subscription.organization_id == org_id)
            .first()
        )
    if subscription is None:
        subscription = (
            db.query(Subscription).filter(Subscription.user_id == user.id).first()
        )

    if subscription is not None and subscription.plan_id:
        from database import Plan

        plan = db.query(Plan).filter(Plan.id == subscription.plan_id).first()
        if plan is not None:
            return plan

    # No subscription record yet (fresh trial) — fall back to the default plan
    return get_default_plan(db)


def user_has_feature(db: Session, user, feature_key: str) -> bool:
    """Check whether a user's active plan grants a feature."""
    return has_plan_feature(get_active_plan(db, user), feature_key)


def require_plan_feature(feature_key: str, detail: Optional[str] = None):
    """
    Build a FastAPI dependency that gates an endpoint behind a plan feature.

    Usage:
        @router.get("/thing", dependencies=[Depends(require_plan_feature(AI_ADVISOR))])

    Raises 403 (not 402) when the plan is valid but lacks the feature — the
    subscription is fine, the tier simply doesn't include it. Callers that need
    the user object should depend on `get_current_active_user` as usual.
    """
    from fastapi import Depends, HTTPException, status

    from auth.dependencies import get_current_active_user
    from database import User, get_db

    message = detail or "Seu plano atual não inclui este recurso."

    def _dependency(
        current_user: "User" = Depends(get_current_active_user),
        db: Session = Depends(get_db),
    ):
        if not user_has_feature(db, current_user, feature_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            )
        return True

    return _dependency
