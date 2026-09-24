"""
Payment Reminders Router — upcoming outgoing payments for the active company.

  GET  /payment-reminders/settings      current user's preference for this company
  PUT  /payment-reminders/settings      update it
  GET  /payment-reminders/preview       live list for today / this week / this month
  POST /payment-reminders/test-email    send the reminder to yourself right now

The preview is computed by the same shared module the scheduled email job uses
(payment_reminders.py), so what the modal shows and what the email lists are
the same list by construction.
"""

import logging
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

import payment_reminders as pr
from auth.dependencies import get_current_active_user
from database import Organization, PaymentReminderSetting, User, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payment-reminders", tags=["Payment Reminders"])
limiter = Limiter(key_func=get_remote_address)

Frequency = Literal["daily", "weekly", "monthly"]


# ─── SCHEMAS ───────────────────────────────────────────────────────────────────


class ReminderSettings(BaseModel):
    email_enabled: bool
    in_app_enabled: bool
    frequency: Frequency


class ReminderSettingsUpdate(BaseModel):
    email_enabled: Optional[bool] = None
    in_app_enabled: Optional[bool] = None
    frequency: Optional[Frequency] = None


class PaymentItem(BaseModel):
    document_id: int
    due_date: str
    amount: float
    amount_label: str
    label: str
    category: Optional[str] = None
    category_label: Optional[str] = None
    payee: Optional[str] = None


class PreviewResponse(BaseModel):
    frequency: Frequency
    start_date: str
    end_date: str
    period_label: str
    period_key: str
    count: int
    total: float
    total_label: str
    items: List[PaymentItem]


# ─── HELPERS ───────────────────────────────────────────────────────────────────


def _active_org_id(user: User) -> Optional[int]:
    return getattr(user, "_active_org_id", None) or getattr(user, "active_org_id", None)


def _get_setting(db: Session, user: User) -> Optional[PaymentReminderSetting]:
    org_id = _active_org_id(user)
    query = db.query(PaymentReminderSetting).filter(PaymentReminderSetting.user_id == user.id)
    if org_id:
        query = query.filter(PaymentReminderSetting.organization_id == org_id)
    else:
        query = query.filter(PaymentReminderSetting.organization_id.is_(None))
    return query.first()


def _to_schema(setting: Optional[PaymentReminderSetting]) -> ReminderSettings:
    if setting is None:
        # Defaults for someone who has never opened the settings: the in-app
        # alert is on (it only appears when something is actually due), email
        # is opt-in.
        return ReminderSettings(email_enabled=False, in_app_enabled=True, frequency="daily")
    frequency = setting.frequency if setting.frequency in pr.FREQUENCIES else "daily"
    return ReminderSettings(
        email_enabled=setting.email_enabled,
        in_app_enabled=setting.in_app_enabled,
        frequency=frequency,
    )


def build_preview(db: Session, user: User, frequency: str) -> PreviewResponse:
    today = pr.today_brazil()
    start, end = pr.reminder_window(frequency, today)
    documents = pr.org_documents_query(db, _active_org_id(user), user.id, end).all()
    payments = pr.collect_upcoming_payments(documents, start, end)
    total = pr.total_amount(payments)

    return PreviewResponse(
        frequency=frequency,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        period_label=pr.format_period_label(frequency, start, end),
        period_key=pr.period_key(frequency, today),
        count=len(payments),
        total=float(total),
        total_label=pr.format_brl(total),
        items=[
            PaymentItem(**p.to_dict(), amount_label=pr.format_brl(p.amount)) for p in payments
        ],
    )


def _company_name(db: Session, user: User) -> str:
    org_id = _active_org_id(user)
    if org_id:
        org = db.query(Organization).filter(Organization.id == org_id).first()
        if org and org.company_name:
            return org.company_name
    return user.company_name or ""


# ─── ENDPOINTS ─────────────────────────────────────────────────────────────────


@router.get("/settings", response_model=ReminderSettings)
async def get_settings(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return _to_schema(_get_setting(db, current_user))


@router.put("/settings", response_model=ReminderSettings)
async def update_settings(
    payload: ReminderSettingsUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    setting = _get_setting(db, current_user)
    if setting is None:
        setting = PaymentReminderSetting(
            user_id=current_user.id,
            organization_id=_active_org_id(current_user),
        )
        db.add(setting)

    if payload.email_enabled is not None:
        setting.email_enabled = payload.email_enabled
    if payload.in_app_enabled is not None:
        setting.in_app_enabled = payload.in_app_enabled
    if payload.frequency is not None and payload.frequency != setting.frequency:
        setting.frequency = payload.frequency
        # A new cadence starts a new series; don't let the old period key
        # suppress the first email of the new one.
        setting.last_sent_period = None

    setting.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(setting)
    return _to_schema(setting)


@router.get("/preview", response_model=PreviewResponse)
async def preview(
    frequency: Optional[Frequency] = Query(
        None, description="daily | weekly | monthly — defaults to the saved preference"
    ),
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    chosen = frequency or _to_schema(_get_setting(db, current_user)).frequency
    return build_preview(db, current_user, chosen)


@router.post("/test-email")
@limiter.limit("5/hour")
async def send_test_email(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Send this period's reminder to the signed-in user, regardless of schedule."""
    from email_service import build_payment_reminder_email, email_service

    frequency = _to_schema(_get_setting(db, current_user)).frequency
    preview_data = build_preview(db, current_user, frequency)

    if preview_data.count == 0:
        return {
            "sent": False,
            "reason": "Nenhum pagamento previsto para o período — não há o que enviar.",
        }

    subject, html = build_payment_reminder_email(
        user_name=current_user.full_name,
        company_name=_company_name(db, current_user),
        frequency=frequency,
        period_label=preview_data.period_label,
        payments=[
            {
                "label": item.label,
                "category_label": item.category_label,
                "due_date": datetime.strptime(item.due_date, "%Y-%m-%d").date(),
                "amount_label": item.amount_label,
            }
            for item in preview_data.items
        ],
        total_label=preview_data.total_label,
        frontend_url=email_service.frontend_url,
    )

    sent = await email_service.send_email(to=current_user.email, subject=subject, html=html)
    if not sent:
        raise HTTPException(
            status_code=502,
            detail="Não foi possível enviar o e-mail agora. Tente novamente em instantes.",
        )
    return {"sent": True, "to": current_user.email, "count": preview_data.count}
