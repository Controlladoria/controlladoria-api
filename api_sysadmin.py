"""
System Admin API Routes

All routes are prefixed with /sysadmin/
Accessed via admin.controlladoria.com.br subdomain.

Requires sysadmin authentication - completely separate from customer API.
"""

from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc

from database import get_db, User, Subscription, Document, JournalEntry
from database_sysadmin import (
    SystemAdmin, ImpersonationSession, SystemAdminAuditLog,
    ErrorLog, SupportTicket, TicketMessage, DailyMetrics
)
from auth.sysadmin_auth import (
    get_current_sysadmin, get_impersonation_context, require_permission,
    create_sysadmin_access_token, create_impersonation_token,
    log_sysadmin_action, current_auth_provider, hash_password
)

router = APIRouter(prefix="/sysadmin", tags=["System Admin"])


# ============================================================================
# AUTHENTICATION
# ============================================================================

class SysAdminLoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: Optional[str] = None


class SysAdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    sysadmin: dict


@router.post("/auth/login", response_model=SysAdminLoginResponse)
async def sysadmin_login(
    request: Request,
    data: SysAdminLoginRequest,
    db: Session = Depends(get_db)
):
    """
    System admin login (separate from customer login)

    Supports:
    - Local password authentication (current)
    - MS Entra SSO (future)
    """
    # Authenticate using current provider
    sysadmin = current_auth_provider.authenticate(
        credentials={"email": data.email, "password": data.password, "mfa_code": data.mfa_code},
        db=db
    )

    if not sysadmin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )

    # Update last login
    sysadmin.last_login = datetime.utcnow()
    sysadmin.last_login_ip = request.client.host
    sysadmin.login_count += 1
    db.commit()

    # Create access token
    access_token = create_sysadmin_access_token(
        data={"sub": sysadmin.id, "email": sysadmin.email}
    )

    # Log login
    log_sysadmin_action(
        db=db,
        sysadmin=sysadmin,
        action="login",
        description="Successful login",
        request_context={
            "ip_address": request.client.host,
            "user_agent": request.headers.get("user-agent")
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "sysadmin": {
            "id": sysadmin.id,
            "email": sysadmin.email,
            "full_name": sysadmin.full_name,
            "permissions": sysadmin.permissions,
            "is_super_admin": sysadmin.is_super_admin,
            "mfa_enabled": sysadmin.mfa_enabled,
        }
    }


@router.get("/auth/me")
async def get_current_sysadmin_info(
    sysadmin: SystemAdmin = Depends(get_current_sysadmin)
):
    """Get current sysadmin info"""
    return {
        "id": sysadmin.id,
        "email": sysadmin.email,
        "full_name": sysadmin.full_name,
        "permissions": sysadmin.permissions,
        "is_super_admin": sysadmin.is_super_admin,
        "mfa_enabled": sysadmin.mfa_enabled,
        "last_login": sysadmin.last_login,
    }


# ============================================================================
# DASHBOARD METRICS
# ============================================================================

@router.get("/dashboard/stats")
async def get_dashboard_stats(
    sysadmin: SystemAdmin = Depends(require_permission("view_metrics")),
    db: Session = Depends(get_db)
):
    """
    Main dashboard overview stats

    Real-time + cached metrics for fast loading.
    """
    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    # Get today's pre-aggregated metrics (if available)
    today_metrics = db.query(DailyMetrics).filter(DailyMetrics.date == today).first()
    yesterday_metrics = db.query(DailyMetrics).filter(DailyMetrics.date == yesterday).first()

    # Active users (logged in last 24h) - real-time
    active_users_24h = db.query(User).filter(
        User.last_login >= datetime.utcnow() - timedelta(hours=24)
    ).count()

    # New registrations (last 7 days)
    new_registrations_7d = db.query(User).filter(
        User.created_at >= datetime.utcnow() - timedelta(days=7)
    ).count()

    # Active subscriptions
    active_subscriptions = db.query(Subscription).filter(
        Subscription.status.in_(["active", "trial"])
    ).count()

    # Total revenue (MRR) - sum of all active subscriptions
    # TODO: Implement when subscription pricing is added
    mrr = 0

    # Error rate (last 24h)
    errors_24h = db.query(ErrorLog).filter(
        ErrorLog.created_at >= datetime.utcnow() - timedelta(hours=24)
    ).count()

    # Open support tickets
    open_tickets = db.query(SupportTicket).filter(
        SupportTicket.status.in_(["open", "assigned", "in_progress"])
    ).count()

    # Documents processed today
    documents_today = db.query(Document).filter(
        func.date(Document.upload_date) == today
    ).count()

    return {
        "active_users_24h": active_users_24h,
        "active_users_trend": calculate_trend(
            active_users_24h,
            yesterday_metrics.active_users_24h if yesterday_metrics else 0
        ),
        "new_registrations_7d": new_registrations_7d,
        "active_subscriptions": active_subscriptions,
        "mrr": mrr,
        "errors_24h": errors_24h,
        "open_tickets": open_tickets,
        "documents_today": documents_today,
        "updated_at": datetime.utcnow(),
    }


@router.get("/dashboard/charts/user-growth")
async def get_user_growth_chart(
    sysadmin: SystemAdmin = Depends(require_permission("view_metrics")),
    days: int = Query(30, ge=7, le=365),
    db: Session = Depends(get_db)
):
    """User growth chart data (last N days)"""
    start_date = datetime.utcnow().date() - timedelta(days=days)

    metrics = db.query(DailyMetrics).filter(
        DailyMetrics.date >= start_date
    ).order_by(DailyMetrics.date).all()

    return {
        "labels": [m.date.isoformat() for m in metrics],
        "datasets": [
            {
                "label": "Total Users",
                "data": [m.total_users for m in metrics],
            },
            {
                "label": "New Registrations",
                "data": [m.new_registrations for m in metrics],
            },
            {
                "label": "Active Users (7d)",
                "data": [m.active_users_7d for m in metrics],
            }
        ]
    }


# ============================================================================
# USER MANAGEMENT
# ============================================================================

@router.get("/users/search")
async def search_users(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, ge=1, le=100),
    sysadmin: SystemAdmin = Depends(require_permission("view_all_users")),
    db: Session = Depends(get_db)
):
    """
    Search for customer users by email, name, CNPJ

    Used for impersonation, support, analytics.
    """
    search_term = f"%{q}%"

    users = db.query(User).filter(
        or_(
            User.email.ilike(search_term),
            User.full_name.ilike(search_term),
            User.company_name.ilike(search_term),
            User.cnpj.ilike(search_term),
        )
    ).limit(limit).all()

    return {
        "results": [
            {
                "id": u.id,
                "email": u.email,
                "full_name": u.full_name,
                "company_name": u.company_name,
                "cnpj": u.cnpj,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at,
                "last_login": u.last_login,
                "parent_user_id": u.parent_user_id,
            }
            for u in users
        ]
    }


@router.get("/users/{user_id}")
async def get_user_details(
    user_id: int,
    sysadmin: SystemAdmin = Depends(require_permission("view_all_users")),
    db: Session = Depends(get_db)
):
    """Get detailed user information"""
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get subscription
    subscription = db.query(Subscription).filter(Subscription.user_id == user_id).first()

    # Get usage stats
    documents_count = db.query(Document).filter(Document.user_id == user_id).count()
    transactions_count = db.query(JournalEntry).filter(JournalEntry.user_id == user_id).count()

    # Get recent errors
    recent_errors = db.query(ErrorLog).filter(
        ErrorLog.user_id == user_id
    ).order_by(desc(ErrorLog.created_at)).limit(5).all()

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "company_name": user.company_name,
            "cnpj": user.cnpj,
            "role": user.role,
            "is_active": user.is_active,
            "email_verified": user.email_verified,
            "created_at": user.created_at,
            "last_login": user.last_login,
            "parent_user_id": user.parent_user_id,
        },
        "subscription": {
            "status": subscription.status if subscription else None,
            "plan": subscription.plan_name if subscription else None,
            "max_users": subscription.max_users if subscription else None,
            "current_period_end": subscription.current_period_end if subscription else None,
        } if subscription else None,
        "usage": {
            "documents_count": documents_count,
            "transactions_count": transactions_count,
        },
        "recent_errors": [
            {
                "id": e.id,
                "error_type": e.error_type,
                "error_message": e.error_message,
                "endpoint": e.endpoint,
                "created_at": e.created_at,
            }
            for e in recent_errors
        ]
    }


# ============================================================================
# IMPERSONATION
# ============================================================================

class ImpersonateUserRequest(BaseModel):
    user_id: int
    reason: str  # Required - why are you impersonating?


@router.post("/impersonate")
async def impersonate_user(
    request: Request,
    data: ImpersonateUserRequest,
    sysadmin: SystemAdmin = Depends(require_permission("impersonate_users")),
    db: Session = Depends(get_db)
):
    """
    Start impersonation session

    Returns special JWT that allows sysadmin to act as customer.
    """
    # Validate reason
    if not data.reason or len(data.reason) < 10:
        raise HTTPException(
            status_code=400,
            detail="Reason must be at least 10 characters"
        )

    # Verify target user exists
    target_user = db.query(User).filter(User.id == data.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Create impersonation session
    session = ImpersonationSession(
        sysadmin_id=sysadmin.id,
        sysadmin_email=sysadmin.email,
        target_user_id=target_user.id,
        target_user_email=target_user.email,
        reason=data.reason,
        ip_address=request.client.host,
        user_agent=request.headers.get("user-agent"),
        auto_expire_at=datetime.utcnow() + timedelta(hours=1),  # Max 1 hour
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Create impersonation token
    token = create_impersonation_token(
        sysadmin=sysadmin,
        target_user_id=target_user.id,
        impersonation_session_id=session.id
    )

    # Log action
    log_sysadmin_action(
        db=db,
        sysadmin=sysadmin,
        action="start_impersonation",
        entity_type="user",
        entity_id=target_user.id,
        description=f"Started impersonating {target_user.email}",
        metadata={"reason": data.reason, "session_id": session.id},
        request_context={
            "ip_address": request.client.host,
            "user_agent": request.headers.get("user-agent")
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "impersonation_session_id": session.id,
        "target_user": {
            "id": target_user.id,
            "email": target_user.email,
            "full_name": target_user.full_name,
            "company_name": target_user.company_name,
        },
        "expires_at": session.auto_expire_at,
    }


@router.post("/impersonate/{session_id}/end")
async def end_impersonation(
    session_id: int,
    sysadmin: SystemAdmin = Depends(get_current_sysadmin),
    db: Session = Depends(get_db)
):
    """End impersonation session"""
    session = db.query(ImpersonationSession).filter(
        ImpersonationSession.id == session_id,
        ImpersonationSession.sysadmin_id == sysadmin.id,
        ImpersonationSession.is_active == True
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # End session
    session.is_active = False
    session.ended_at = datetime.utcnow()
    session.duration_seconds = int((session.ended_at - session.started_at).total_seconds())
    db.commit()

    # Log action
    log_sysadmin_action(
        db=db,
        sysadmin=sysadmin,
        action="end_impersonation",
        entity_type="impersonation_session",
        entity_id=session_id,
        description=f"Ended impersonation of {session.target_user_email}"
    )

    return {"message": "Impersonation session ended"}


@router.get("/impersonation/sessions")
async def list_impersonation_sessions(
    limit: int = Query(50, ge=1, le=200),
    sysadmin: SystemAdmin = Depends(get_current_sysadmin),
    db: Session = Depends(get_db)
):
    """List all impersonation sessions (audit trail)"""
    sessions = db.query(ImpersonationSession).order_by(
        desc(ImpersonationSession.started_at)
    ).limit(limit).all()

    return {
        "sessions": [
            {
                "id": s.id,
                "sysadmin_email": s.sysadmin_email,
                "target_user_email": s.target_user_email,
                "reason": s.reason,
                "started_at": s.started_at,
                "ended_at": s.ended_at,
                "duration_seconds": s.duration_seconds,
                "is_active": s.is_active,
            }
            for s in sessions
        ]
    }


# ============================================================================
# ERROR TRACKING
# ============================================================================

@router.get("/errors")
async def list_errors(
    limit: int = Query(100, ge=1, le=500),
    error_type: Optional[str] = None,
    endpoint: Optional[str] = None,
    user_id: Optional[int] = None,
    unresolved_only: bool = False,
    sysadmin: SystemAdmin = Depends(require_permission("view_errors")),
    db: Session = Depends(get_db)
):
    """List recent errors with filtering"""
    query = db.query(ErrorLog).order_by(desc(ErrorLog.created_at))

    if error_type:
        query = query.filter(ErrorLog.error_type == error_type)

    if endpoint:
        query = query.filter(ErrorLog.endpoint.ilike(f"%{endpoint}%"))

    if user_id:
        query = query.filter(ErrorLog.user_id == user_id)

    if unresolved_only:
        query = query.filter(ErrorLog.is_resolved == False)

    errors = query.limit(limit).all()

    return {
        "errors": [
            {
                "id": e.id,
                "error_type": e.error_type,
                "error_message": e.error_message,
                "endpoint": e.endpoint,
                "method": e.method,
                "status_code": e.status_code,
                "user_id": e.user_id,
                "user_email": e.user_email,
                "created_at": e.created_at,
                "is_resolved": e.is_resolved,
            }
            for e in errors
        ]
    }


@router.get("/errors/{error_id}")
async def get_error_details(
    error_id: int,
    sysadmin: SystemAdmin = Depends(require_permission("view_errors")),
    db: Session = Depends(get_db)
):
    """Get full error details including stack trace"""
    error = db.query(ErrorLog).filter(ErrorLog.id == error_id).first()

    if not error:
        raise HTTPException(status_code=404, detail="Error not found")

    return {
        "id": error.id,
        "error_type": error.error_type,
        "error_message": error.error_message,
        "stack_trace": error.stack_trace,
        "endpoint": error.endpoint,
        "method": error.method,
        "status_code": error.status_code,
        "user_id": error.user_id,
        "user_email": error.user_email,
        "organization_id": error.organization_id,
        "request_body": error.request_body,
        "request_headers": error.request_headers,
        "query_params": error.query_params,
        "ip_address": error.ip_address,
        "user_agent": error.user_agent,
        "response_time_ms": error.response_time_ms,
        "created_at": error.created_at,
        "is_resolved": error.is_resolved,
        "resolved_at": error.resolved_at,
        "resolution_notes": error.resolution_notes,
    }


# Helper functions

def calculate_trend(current: int, previous: int) -> dict:
    """Calculate percentage change for trends"""
    if previous == 0:
        return {"direction": "up" if current > 0 else "flat", "percentage": 0}

    change = ((current - previous) / previous) * 100

    return {
        "direction": "up" if change > 0 else "down" if change < 0 else "flat",
        "percentage": abs(round(change, 1))
    }
