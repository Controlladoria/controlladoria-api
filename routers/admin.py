"""
Admin Router
Handles admin dashboard endpoints with TENANT ISOLATION:
- Admin statistics (tenant-scoped)
- User management (tenant-scoped)
- Recent activity (tenant-scoped)
- Audit logs (tenant-scoped)

IMPORTANT: All queries filter by accessible_user_ids for multi-tenant isolation
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth.dependencies import get_current_active_user
from auth.permissions import Permission, get_accessible_user_ids, require_permission
from database import (
    AuditLog,
    ContactSubmission,
    Document,
    DocumentStatus,
    Subscription,
    User,
    get_db,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
async def get_admin_stats(
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)
):
    """
    Get comprehensive admin statistics

    Requires admin.dashboard permission
    Returns system-wide metrics for admin dashboard (TENANT-SCOPED)
    """
    require_permission(current_user, Permission.ADMIN_DASHBOARD)

    # Get accessible users in current tenant
    accessible_user_ids = get_accessible_user_ids(current_user, db)

    # User statistics (filtered by tenant)
    total_users = db.query(func.count(User.id)).filter(User.id.in_(accessible_user_ids)).scalar()
    active_users = db.query(func.count(User.id)).filter(User.id.in_(accessible_user_ids), User.is_active == True).scalar()
    verified_users = (
        db.query(func.count(User.id)).filter(User.id.in_(accessible_user_ids), User.is_verified == True).scalar()
    )

    # Subscription statistics (filtered by tenant)
    total_subscriptions = db.query(func.count(Subscription.id)).filter(Subscription.user_id.in_(accessible_user_ids)).scalar()
    active_subscriptions = (
        db.query(func.count(Subscription.id))
        .filter(Subscription.user_id.in_(accessible_user_ids), Subscription.status.in_(["active", "trialing"]))
        .scalar()
    )
    trialing_subscriptions = (
        db.query(func.count(Subscription.id))
        .filter(Subscription.user_id.in_(accessible_user_ids), Subscription.status == "trialing")
        .scalar()
    )
    canceled_subscriptions = (
        db.query(func.count(Subscription.id))
        .filter(Subscription.user_id.in_(accessible_user_ids), Subscription.cancel_at_period_end == True)
        .scalar()
    )

    # Document statistics (filtered by tenant)
    total_documents = db.query(func.count(Document.id)).filter(Document.user_id.in_(accessible_user_ids)).scalar()
    completed_documents = (
        db.query(func.count(Document.id))
        .filter(Document.user_id.in_(accessible_user_ids), Document.status == DocumentStatus.COMPLETED)
        .scalar()
    )
    failed_documents = (
        db.query(func.count(Document.id))
        .filter(Document.user_id.in_(accessible_user_ids), Document.status == DocumentStatus.FAILED)
        .scalar()
    )
    processing_documents = (
        db.query(func.count(Document.id))
        .filter(Document.user_id.in_(accessible_user_ids), Document.status == DocumentStatus.PROCESSING)
        .scalar()
    )

    # Contact submissions (no tenant filtering - contact form is public)
    # NOTE: Contact submissions should probably only be in SYSADMIN, not tenant admin
    total_contacts = db.query(func.count(ContactSubmission.id)).scalar()
    unread_contacts = (
        db.query(func.count(ContactSubmission.id))
        .filter(ContactSubmission.read == 0)
        .scalar()
    )

    # Recent activity (last 7 days) - tenant filtered
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    new_users_week = (
        db.query(func.count(User.id))
        .filter(User.id.in_(accessible_user_ids), User.created_at >= seven_days_ago)
        .scalar()
    )
    new_documents_week = (
        db.query(func.count(Document.id))
        .filter(Document.user_id.in_(accessible_user_ids), Document.upload_date >= seven_days_ago)
        .scalar()
    )

    return {
        "users": {
            "total": total_users,
            "active": active_users,
            "verified": verified_users,
            "new_this_week": new_users_week,
        },
        "subscriptions": {
            "total": total_subscriptions,
            "active": active_subscriptions,
            "trialing": trialing_subscriptions,
            "canceled": canceled_subscriptions,
        },
        "documents": {
            "total": total_documents,
            "completed": completed_documents,
            "failed": failed_documents,
            "processing": processing_documents,
            "new_this_week": new_documents_week,
        },
        "contacts": {"total": total_contacts, "unread": unread_contacts},
    }


@router.get("/users")
async def list_all_users(
    current_user: User = Depends(get_current_active_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    List all users (admin only) - TENANT-SCOPED

    Returns paginated list of users in current tenant with their subscription status
    """
    require_permission(current_user, Permission.ADMIN_VIEW_USERS)

    # Only show users in current user's tenant (multi-tenant isolation)
    accessible_ids = get_accessible_user_ids(current_user, db)
    users = db.query(User).filter(User.id.in_(accessible_ids)).offset(skip).limit(limit).all()

    users_data = []
    for user in users:
        user_dict = {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "company_name": user.company_name,
            "cnpj": user.cnpj,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_admin": user.is_admin,
            "created_at": user.created_at.isoformat() + "Z" if user.created_at else None,
            "subscription": None,
        }

        # Add subscription info if exists (pick active org's subscription, or first available)
        sub = next(
            (s for s in user.subscriptions if s.organization_id == user.active_org_id),
            user.subscriptions[0] if user.subscriptions else None,
        )
        if sub:
            user_dict["subscription"] = {
                "status": (
                    sub.status.value if sub.status else None
                ),
                "trial_end": (
                    sub.trial_end.isoformat() + "Z"
                    if sub.trial_end
                    else None
                ),
                "cancel_at_period_end": sub.cancel_at_period_end,
            }

        users_data.append(user_dict)

    # Get total count within tenant
    total_users = db.query(func.count(User.id)).filter(User.id.in_(accessible_ids)).scalar()

    return {"users": users_data, "total": total_users, "skip": skip, "limit": limit}


@router.get("/recent-activity")
async def get_recent_activity(
    current_user: User = Depends(get_current_active_user),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """
    Get recent platform activity (admin only) - TENANT-SCOPED

    Returns recent user registrations, document uploads, and contact submissions
    All filtered by tenant for multi-tenant isolation
    """
    require_permission(current_user, Permission.ADMIN_DASHBOARD)

    # Get accessible users in current tenant
    accessible_user_ids = get_accessible_user_ids(current_user, db)

    # Recent users (filtered by tenant)
    recent_users = db.query(User).filter(User.id.in_(accessible_user_ids)).order_by(User.created_at.desc()).limit(limit).all()

    # Recent documents (filtered by tenant)
    recent_documents = (
        db.query(Document).filter(Document.user_id.in_(accessible_user_ids)).order_by(Document.upload_date.desc()).limit(limit).all()
    )

    # Recent contacts (no tenant filtering - contact form is public)
    # TODO: Contact submissions should probably only be in SYSADMIN, not tenant admin
    recent_contacts = (
        db.query(ContactSubmission)
        .order_by(ContactSubmission.submitted_date.desc())
        .limit(limit)
        .all()
    )

    return {
        "recent_users": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "company_name": u.company_name,
                "created_at": u.created_at.isoformat() + "Z" if u.created_at else None,
                "last_login": u.last_login.isoformat() + "Z" if u.last_login else None,
            }
            for u in recent_users
        ],
        "recent_documents": [
            {
                "id": d.id,
                "file_name": d.file_name,
                "file_type": d.file_type,
                "status": d.status.value,
                "upload_date": d.upload_date.isoformat() + "Z" if d.upload_date else None,
                "user_email": d.user.email if d.user else None,
            }
            for d in recent_documents
        ],
        "recent_contacts": [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "message": (
                    c.message[:100] + "..." if len(c.message) > 100 else c.message
                ),
                "submitted_date": (
                    c.submitted_date.isoformat() + "Z" if c.submitted_date else None
                ),
                "read": c.read == 1,
            }
            for c in recent_contacts
        ],
    }


@router.get("/audit-logs")
async def get_audit_logs(
    current_user: User = Depends(get_current_active_user),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get audit logs (admin only) - TENANT-SCOPED

    Supports filtering by:
    - user_id: Filter by specific user (within tenant)
    - action: Filter by action type (create, update, delete)
    - entity_type: Filter by entity type (document, transaction, etc)
    - date_from/date_to: Filter by date range (ISO format)

    Returns paginated audit log entries with full details.
    All logs filtered by tenant for multi-tenant isolation.
    """
    require_permission(current_user, Permission.ADMIN_VIEW_AUDIT_LOGS)

    # Build query - admin sees all company logs (TENANT-SCOPED)
    accessible_user_ids = get_accessible_user_ids(current_user, db)
    query = db.query(AuditLog).filter(AuditLog.user_id.in_(accessible_user_ids))

    # Apply filters
    if user_id:
        # Verify user_id is in accessible tenant
        if user_id not in accessible_user_ids:
            raise HTTPException(status_code=403, detail="Acesso negado a este usuário")
        query = query.filter(AuditLog.user_id == user_id)

    if action:
        query = query.filter(AuditLog.action == action)

    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)

    if date_from:
        try:
            from_date = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
            query = query.filter(AuditLog.created_at >= from_date)
        except:
            pass

    if date_to:
        try:
            to_date = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
            query = query.filter(AuditLog.created_at <= to_date)
        except:
            pass

    # Get total count
    total = query.count()

    # Paginate
    offset = (page - 1) * page_size
    logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size).all()

    return {
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "user_email": log.user.email if log.user else None,
                "user_name": log.user.full_name if log.user else None,
                "document_id": log.document_id,
                "action": log.action,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "before_value": log.before_value,
                "after_value": log.after_value,
                "changes_summary": log.changes_summary,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "created_at": log.created_at.isoformat() + "Z" if log.created_at else None,  # Add Z to indicate UTC
            }
            for log in logs
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        }
    }


@router.get("/ai-pool-stats")
async def get_ai_pool_stats(
    current_user: User = Depends(get_current_active_user),
):
    """
    Get AI key pool statistics (key health, request counts, availability).

    Requires admin.dashboard permission.
    Never exposes full API keys — only last 6 characters.
    """
    require_permission(current_user, Permission.ADMIN_DASHBOARD)

    try:
        # Get processor instance from documents router (module-level singleton)
        import routers.documents as docs_router
        processor = getattr(docs_router, "processor", None)
        if not processor or not hasattr(processor, "key_pool"):
            return {"error": "AI key pool not initialized", "stats": {}}

        return {
            "ai_provider": processor.ai_provider,
            "failover_enabled": processor.ai_failover_enabled,
            "stats": processor.key_pool.get_stats(),
        }
    except Exception as e:
        logger.error(f"Error getting AI pool stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get AI pool stats")
