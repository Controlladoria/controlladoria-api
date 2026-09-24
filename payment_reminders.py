"""
Payment reminders — which outgoing payments are coming up for an organization.

Shared verbatim between controlladoria-api (the in-app preview) and
controlladoria-jobs (the scheduled email), so the list a user sees on screen
and the list they receive by email can never disagree. Keep the two copies
identical.

The rules
---------
A movement is a reminder-worthy payment when all of these hold:

  1. It is outgoing: despesa, custo or investimento. Revenue, losses and
     non-cash lines (depreciação, amortização, provisões) are never payments,
     and neither are transfers between the company's own accounts.
  2. Its payment date falls inside the reminder window, and the window always
     starts *today*. Earlier days of the period are dropped: if the monthly
     reminder is read on the 2nd, the payment dated the 1st is assumed paid.
  3. It was registered *before* its payment date. Something dated today that
     was only entered today is a record of a payment already made, not an
     obligation to remember.
  4. It is not already marked as paid (a receipt / comprovante).

Payment date
------------
Boletos, DARFs and DAS carry a vencimento in ``payment_info.due_date``. That is
preferred over the movement date, because the date users confirm during
validation is the *emission* date — a DARF emitted on the 1st and due on the
24th would otherwise never produce a reminder. Movements without a due date
fall back to their own date.
"""

from __future__ import annotations

import calendar
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

BRT = timezone(timedelta(hours=-3))

FREQUENCY_DAILY = "daily"
FREQUENCY_WEEKLY = "weekly"
FREQUENCY_MONTHLY = "monthly"
FREQUENCIES = (FREQUENCY_DAILY, FREQUENCY_WEEKLY, FREQUENCY_MONTHLY)

OUTGOING_TYPES = {"despesa", "custo", "investimento"}

# Categories that are booked as outgoing but never involve paying anyone.
NON_PAYMENT_CATEGORIES = {
    "transferencia_interna",  # between the company's own accounts
    "depreciacao",
    "amortizacao",
    "provisoes",
    "perdas",
}

_INCOME_ALIASES = {"income", "receita", "entrada", "crédito", "credito", "revenue", "credit"}
_COST_ALIASES = {"custo", "cost"}

MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


# ─── WINDOWS ───────────────────────────────────────────────────────────────────


def today_brazil() -> date:
    return datetime.now(BRT).date()


def reminder_window(frequency: str, today: date) -> Tuple[date, date]:
    """
    The span of payment dates a reminder covers, always starting today.

    daily   → today
    weekly  → today .. Sunday of this week
    monthly → today .. last day of this month
    """
    if frequency == FREQUENCY_WEEKLY:
        return today, today + timedelta(days=6 - today.weekday())
    if frequency == FREQUENCY_MONTHLY:
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today, today.replace(day=last_day)
    return today, today


def is_send_day(frequency: str, today: date) -> bool:
    """Daily every day, weekly on Mondays, monthly on the 1st."""
    if frequency == FREQUENCY_WEEKLY:
        return today.weekday() == 0
    if frequency == FREQUENCY_MONTHLY:
        return today.day == 1
    return True


def period_key(frequency: str, today: date) -> str:
    """
    Stable id for the period a reminder belongs to. The job stores it after a
    successful send, so a retried or double-fired run cannot email twice.
    """
    if frequency == FREQUENCY_WEEKLY:
        year, week, _ = today.isocalendar()
        return f"W{year}-{week:02d}"
    if frequency == FREQUENCY_MONTHLY:
        return f"M{today.year}-{today.month:02d}"
    return f"D{today.isoformat()}"


def format_period_label(frequency: str, start: date, end: date) -> str:
    """Human label used in the email subject/body and the preview modal."""
    if frequency == FREQUENCY_WEEKLY:
        if start == end:
            return f"hoje, {format_long_date(start)}"
        return f"esta semana ({start.strftime('%d/%m')} a {end.strftime('%d/%m')})"
    if frequency == FREQUENCY_MONTHLY:
        return f"{MONTHS_PT[start.month - 1]} de {start.year}"
    return f"hoje, {format_long_date(start)}"


def format_long_date(d: date) -> str:
    return f"{d.day} de {MONTHS_PT[d.month - 1]} de {d.year}"


def format_brl(value: Decimal) -> str:
    """R$ 1.234,56"""
    quantized = Decimal(value).quantize(Decimal("0.01"))
    text = f"{quantized:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {text}"


# ─── PARSING HELPERS ───────────────────────────────────────────────────────────


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _to_decimal(value) -> Optional[Decimal]:
    """Accepts numbers, '1234.56' and Brazilian '1.234,56'."""
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _normalize_type(raw) -> Optional[str]:
    """Same mapping the reports use, except transfers are kept distinct."""
    value = str(raw or "").lower().strip()
    if value in _INCOME_ALIASES:
        return "receita"
    if value in _COST_ALIASES:
        return "custo"
    if value in ("investimento", "perda"):
        return value
    if value.startswith("transfer"):
        return "transferencia"
    return "despesa"


def added_on_brazil(upload_date) -> Optional[date]:
    """
    The Brazil-local calendar day a document was registered.

    upload_date is written as a timezone-aware BRT datetime into a naive
    column; with no session timezone set, Postgres (UTC on RDS) stores the UTC
    wall-clock. So naive values are read back as UTC.
    """
    if upload_date is None:
        return None
    if isinstance(upload_date, datetime):
        aware = upload_date if upload_date.tzinfo else upload_date.replace(tzinfo=timezone.utc)
        return aware.astimezone(BRT).date()
    return _parse_date(upload_date)


def _category_display(category: Optional[str]) -> Optional[str]:
    if not category:
        return None
    try:
        from accounting.categories import DRE_CATEGORIES, resolve_category_name

        key = resolve_category_name(category) or category
        return DRE_CATEGORIES.get(key, {}).get("display_name") or category
    except Exception:
        return category


# ─── RESULT ────────────────────────────────────────────────────────────────────


@dataclass
class UpcomingPayment:
    document_id: int
    due_date: date
    amount: Decimal
    label: str
    category: Optional[str]
    category_label: Optional[str]
    payee: Optional[str]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["due_date"] = self.due_date.isoformat()
        data["amount"] = float(self.amount)
        return data


def _pick_label(*candidates: Optional[str]) -> str:
    for candidate in candidates:
        if candidate and str(candidate).strip():
            return " ".join(str(candidate).split())[:120]
    return "Pagamento"


# ─── COLLECTION ────────────────────────────────────────────────────────────────


def _qualifies(
    txn_type: str,
    category: Optional[str],
    due: Optional[date],
    added_on: Optional[date],
    start: date,
    end: date,
) -> bool:
    if txn_type not in OUTGOING_TYPES:
        return False
    if category and category in NON_PAYMENT_CATEGORIES:
        return False
    if due is None or not (start <= due <= end):
        return False
    # Registered on or after the day it was due → already paid, not a reminder.
    if added_on is not None and added_on >= due:
        return False
    return True


def collect_upcoming_payments(
    documents: Iterable, start: date, end: date
) -> List[UpcomingPayment]:
    """
    Upcoming outgoing payments across ``documents`` with a payment date in
    [start, end]. Each document needs ``id``, ``upload_date`` and
    ``extracted_data_json`` — ORM rows or plain objects both work.
    """
    results: List[UpcomingPayment] = []

    for doc in documents:
        try:
            data = json.loads(doc.extracted_data_json) if doc.extracted_data_json else None
        except (TypeError, ValueError):
            continue
        if not isinstance(data, dict):
            continue

        added_on = added_on_brazil(getattr(doc, "upload_date", None))
        issuer = data.get("issuer")
        payee = (issuer.get("name") or issuer.get("legal_name")) if isinstance(issuer, dict) else None

        inner = data.get("transactions")
        if isinstance(inner, list) and inner:
            # Multi-row ledger: each row carries its own date.
            for txn in inner:
                if not isinstance(txn, dict):
                    continue
                txn_type = _normalize_type(txn.get("transaction_type") or data.get("transaction_type"))
                category = txn.get("category")
                due = _parse_date(txn.get("date"))
                if not _qualifies(txn_type, category, due, added_on, start, end):
                    continue
                amount = _to_decimal(txn.get("amount"))
                if not amount:
                    continue
                category_label = _category_display(category)
                results.append(
                    UpcomingPayment(
                        document_id=doc.id,
                        due_date=due,
                        amount=abs(amount),
                        label=_pick_label(txn.get("description"), txn.get("counterparty"), category_label),
                        category=category,
                        category_label=category_label,
                        payee=txn.get("counterparty"),
                    )
                )
            continue

        # Single document (boleto, DARF, nota, manual entry).
        payment_info = data.get("payment_info") or {}
        if not isinstance(payment_info, dict):
            payment_info = {}
        status = str(payment_info.get("status") or "").lower()
        if status == "paid" or payment_info.get("payment_date"):
            continue  # a receipt — already settled

        txn_type = _normalize_type(data.get("transaction_type"))
        category = data.get("category")
        due = _parse_date(payment_info.get("due_date")) or _parse_date(data.get("issue_date"))
        if not _qualifies(txn_type, category, due, added_on, start, end):
            continue

        amount = _to_decimal(data.get("total_amount")) or _to_decimal(data.get("subtotal"))
        if not amount:
            continue

        category_label = _category_display(category)
        results.append(
            UpcomingPayment(
                document_id=doc.id,
                due_date=due,
                amount=abs(amount),
                label=_pick_label(data.get("description"), payee, category_label),
                category=category,
                category_label=category_label,
                payee=payee,
            )
        )

    results.sort(key=lambda p: (p.due_date, -p.amount))
    return results


def total_amount(payments: Iterable[UpcomingPayment]) -> Decimal:
    return sum((p.amount for p in payments), Decimal("0"))


# ─── DOCUMENT SCOPE ────────────────────────────────────────────────────────────


def org_documents_query(db, organization_id: Optional[int], user_id: int, window_end: date):
    """
    Completed documents visible to a member of ``organization_id``.

    Mirrors auth.permissions.document_org_filter (org documents, plus legacy
    documents with no org owned by active members), but works without a
    request-bound user so the scheduled job can use it too.

    Documents registered after the window closes cannot qualify (rule 3), so
    they are cut at the database instead of being parsed.
    """
    from sqlalchemy import or_

    from database import Document, DocumentStatus, OrgMembership

    query = db.query(Document.id, Document.upload_date, Document.extracted_data_json).filter(
        Document.status == DocumentStatus.COMPLETED,
        Document.extracted_data_json.isnot(None),
    )

    if organization_id:
        member_ids = [
            row[0]
            for row in db.query(OrgMembership.user_id)
            .filter_by(organization_id=organization_id, is_active=True)
            .all()
        ] or [user_id]
        query = query.filter(
            or_(
                Document.organization_id == organization_id,
                (Document.organization_id.is_(None)) & (Document.user_id.in_(member_ids)),
            )
        )
    else:
        query = query.filter(Document.user_id == user_id)

    # upload_date holds UTC wall-clock (see added_on_brazil); the window ends at
    # midnight BRT after window_end, i.e. 03:00 UTC.
    cutoff_utc = datetime.combine(window_end + timedelta(days=1), datetime.min.time()) + timedelta(hours=3)
    return query.filter(Document.upload_date < cutoff_utc)
