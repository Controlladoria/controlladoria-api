"""
Tests for upcoming-payment reminders.

The first half pins the reminder rules themselves (payment_reminders.py, the
module shared with the email job); the second half covers the HTTP endpoints
and the email template.
"""

import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

os.environ.setdefault("USE_S3", "false")
os.environ.setdefault("S3_BUCKET_NAME", "dummy")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-reminder-tests")
os.environ.setdefault("AI_PROVIDER", "gemini")
os.environ.setdefault("GEMINI_API_KEY", "fake-key")

import payment_reminders as pr  # noqa: E402

UTC = timezone.utc


class Doc:
    """Stand-in for a Document row: the three columns the module reads."""

    _ids = iter(range(1, 10_000))

    def __init__(self, data: dict, added: datetime):
        self.id = next(Doc._ids)
        self.extracted_data_json = json.dumps(data)
        # Stored as naive UTC wall-clock, like Postgres does (see added_on_brazil)
        self.upload_date = added.astimezone(UTC).replace(tzinfo=None) if added.tzinfo else added


def brt(y, m, d, hour=9):
    return datetime(y, m, d, hour, tzinfo=pr.BRT)


def single(amount, day, *, category="aluguel", txn_type="despesa", due=None, status=None,
           payment_date=None, description=None, issuer=None):
    data = {
        "document_type": "expense",
        "issue_date": day,
        "transaction_type": txn_type,
        "category": category,
        "total_amount": amount,
    }
    if description:
        data["description"] = description
    if issuer:
        data["issuer"] = {"name": issuer}
    if due or status or payment_date:
        data["payment_info"] = {"due_date": due, "status": status, "payment_date": payment_date}
    return data


def ledger(*rows):
    return {"document_type": "transaction_ledger", "transactions": list(rows)}


def row(amount, day, *, txn_type="despesa", category="aluguel", description="linha"):
    return {"date": day, "amount": amount, "transaction_type": txn_type,
            "category": category, "description": description}


def collect(docs, frequency, today):
    start, end = pr.reminder_window(frequency, today)
    return pr.collect_upcoming_payments(docs, start, end)


# ─── WINDOWS ───────────────────────────────────────────────────────────────────


def test_daily_window_is_just_today():
    assert pr.reminder_window("daily", date(2026, 9, 24)) == (date(2026, 9, 24), date(2026, 9, 24))


def test_weekly_window_runs_from_today_to_sunday():
    wednesday = date(2026, 9, 23)
    assert pr.reminder_window("weekly", wednesday) == (wednesday, date(2026, 9, 27))


def test_monthly_window_runs_from_today_to_month_end():
    assert pr.reminder_window("monthly", date(2026, 5, 1)) == (date(2026, 5, 1), date(2026, 5, 31))
    assert pr.reminder_window("monthly", date(2026, 2, 10)) == (date(2026, 2, 10), date(2026, 2, 28))


def test_send_days():
    monday, tuesday = date(2026, 9, 21), date(2026, 9, 22)
    assert pr.is_send_day("daily", tuesday)
    assert pr.is_send_day("weekly", monday) and not pr.is_send_day("weekly", tuesday)
    assert pr.is_send_day("monthly", date(2026, 10, 1)) and not pr.is_send_day("monthly", date(2026, 10, 2))


def test_period_keys_are_stable_per_period():
    assert pr.period_key("daily", date(2026, 9, 24)) == "D2026-09-24"
    assert pr.period_key("monthly", date(2026, 9, 1)) == pr.period_key("monthly", date(2026, 9, 30))
    assert pr.period_key("weekly", date(2026, 9, 21)) == pr.period_key("weekly", date(2026, 9, 27))
    assert pr.period_key("weekly", date(2026, 9, 27)) != pr.period_key("weekly", date(2026, 9, 28))


# ─── THE RULES AS SPECIFIED ────────────────────────────────────────────────────


def test_monthly_preview_on_the_first_lists_the_whole_month():
    """'if I want a monthly preview for May … when I'm in May 1st'"""
    docs = [
        Doc(single(100, "2026-05-01"), brt(2026, 4, 20)),
        Doc(single(200, "2026-05-15"), brt(2026, 4, 20)),
        Doc(single(300, "2026-05-31"), brt(2026, 4, 20)),
        Doc(single(999, "2026-06-01"), brt(2026, 4, 20)),  # next month
    ]
    payments = collect(docs, "monthly", date(2026, 5, 1))
    assert [p.amount for p in payments] == [100, 200, 300]


def test_a_day_that_already_passed_is_assumed_paid():
    """'if in may 2 we send the reminder, and you had a payment in may 1, you dont send it'"""
    docs = [
        Doc(single(100, "2026-05-01"), brt(2026, 4, 20)),
        Doc(single(200, "2026-05-15"), brt(2026, 4, 20)),
    ]
    payments = collect(docs, "monthly", date(2026, 5, 2))
    assert [p.amount for p in payments] == [200]


def test_something_entered_on_its_own_date_is_not_a_reminder():
    """Adding 'I paid X today' today is a record, not an upcoming payment."""
    today = date(2026, 9, 24)
    docs = [
        Doc(single(100, "2026-09-24"), brt(2026, 9, 24, 15)),  # entered same day
        Doc(single(200, "2026-09-24"), brt(2026, 9, 23, 18)),  # entered the day before
    ]
    assert [p.amount for p in collect(docs, "daily", today)] == [200]


def test_future_payment_entered_today_is_included():
    today = date(2026, 9, 24)
    docs = [Doc(single(500, "2026-09-26"), brt(2026, 9, 24, 15))]
    assert [p.amount for p in collect(docs, "weekly", today)] == [500]


def test_added_date_is_read_in_brazil_time():
    """
    Postgres stores UTC wall-clock. 01:00 UTC on the 24th is 22:00 BRT on the
    23rd — so a payment due the 24th counts as entered the day before.
    """
    doc = Doc(single(100, "2026-09-24"), datetime(2026, 9, 24, 1, 0))  # naive UTC
    assert pr.added_on_brazil(doc.upload_date) == date(2026, 9, 23)
    assert len(collect([doc], "daily", date(2026, 9, 24))) == 1


# ─── WHAT COUNTS AS A PAYMENT ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "txn_type,category,included",
    [
        ("despesa", "aluguel", True),
        ("custo", "materia_prima", True),
        ("investimento", "aluguel", True),
        ("receita", "receita_servicos", False),
        ("perda", "perdas", False),
        ("despesa", "depreciacao", False),        # non-cash
        ("despesa", "amortizacao", False),        # intangible write-off, non-cash
        ("despesa", "amortizacao_divida", True),  # loan installment: real cash
        ("despesa", "provisoes", False),
        ("transferencia", "transferencia_interna", False),
    ],
)
def test_only_real_outgoing_payments_count(txn_type, category, included):
    docs = [Doc(single(100, "2026-09-24", txn_type=txn_type, category=category), brt(2026, 9, 1))]
    assert bool(collect(docs, "daily", date(2026, 9, 24))) is included


def test_due_date_wins_over_emission_date():
    """A DARF emitted on the 1st and due on the 24th reminds on the 24th."""
    darf = single(1000, "2026-09-01", category="irpj", due="2026-09-24")
    docs = [Doc(darf, brt(2026, 9, 2))]
    assert [p.due_date for p in collect(docs, "daily", date(2026, 9, 24))] == [date(2026, 9, 24)]
    assert collect(docs, "daily", date(2026, 9, 1)) == []


def test_receipts_are_already_paid():
    docs = [
        Doc(single(100, "2026-09-24", status="paid"), brt(2026, 9, 1)),
        Doc(single(200, "2026-09-24", payment_date="2026-09-20"), brt(2026, 9, 1)),
        Doc(single(300, "2026-09-24", status="pending"), brt(2026, 9, 1)),
    ]
    assert [p.amount for p in collect(docs, "daily", date(2026, 9, 24))] == [300]


def test_ledger_rows_are_evaluated_individually():
    sheet = ledger(
        row(100, "2026-09-24"),
        row(200, "2026-09-25"),
        row(300, "2026-09-24", txn_type="receita"),
        row(400, "2026-09-20"),
    )
    docs = [Doc(sheet, brt(2026, 9, 1))]
    assert [p.amount for p in collect(docs, "weekly", date(2026, 9, 24))] == [100, 200]


def test_amount_formats_and_signs():
    docs = [
        Doc(single("1.234,56", "2026-09-24"), brt(2026, 9, 1)),
        Doc(ledger(row(-250, "2026-09-24")), brt(2026, 9, 1)),  # bank debit
        Doc(single(None, "2026-09-24"), brt(2026, 9, 1)),        # unknown amount: skipped
    ]
    amounts = sorted(p.amount for p in collect(docs, "daily", date(2026, 9, 24)))
    assert amounts == [Decimal("250"), Decimal("1234.56")]


def test_labels_fall_back_to_payee_then_category():
    docs = [
        Doc(single(1, "2026-09-24", description="Aluguel sala 3"), brt(2026, 9, 1)),
        Doc(single(2, "2026-09-24", issuer="Receita Federal", category="irpj"), brt(2026, 9, 1)),
        Doc(single(3, "2026-09-24", category="simples_nacional"), brt(2026, 9, 1)),
    ]
    labels = {p.amount: p.label for p in collect(docs, "daily", date(2026, 9, 24))}
    assert labels[1] == "Aluguel sala 3"
    assert labels[2] == "Receita Federal"
    assert labels[3] == "Simples Nacional"


def test_corrupt_documents_are_skipped_not_fatal():
    bad = Doc({}, brt(2026, 9, 1))
    bad.extracted_data_json = "{not json"
    good = Doc(single(100, "2026-09-24"), brt(2026, 9, 1))
    assert [p.amount for p in collect([bad, good], "daily", date(2026, 9, 24))] == [100]


def test_sorted_by_date_then_largest_first():
    docs = [
        Doc(single(50, "2026-09-25"), brt(2026, 9, 1)),
        Doc(single(10, "2026-09-24"), brt(2026, 9, 1)),
        Doc(single(90, "2026-09-24"), brt(2026, 9, 1)),
    ]
    assert [p.amount for p in collect(docs, "weekly", date(2026, 9, 24))] == [90, 10, 50]


def test_brl_formatting():
    assert pr.format_brl(Decimal("1234.5")) == "R$ 1.234,50"
    assert pr.format_brl(Decimal("0")) == "R$ 0,00"


# ─── EMAIL TEMPLATE ────────────────────────────────────────────────────────────


def _render(**overrides):
    from email_service import build_payment_reminder_email

    kwargs = dict(
        user_name="Mateus Palacio",
        company_name="Padaria do Bairro LTDA",
        frequency="daily",
        period_label="hoje, 24 de setembro de 2026",
        payments=[
            {"label": "IRPJ", "category_label": "IRPJ", "due_date": date(2026, 9, 24), "amount_label": "R$ 1.000,00"},
            {"label": "Simples Nacional", "category_label": None, "due_date": date(2026, 9, 24), "amount_label": "R$ 250,00"},
        ],
        total_label="R$ 1.250,00",
        frontend_url="https://app.controlladoria.com.br",
    )
    kwargs.update(overrides)
    return build_payment_reminder_email(**kwargs)


def test_email_greets_by_first_name_and_lists_everything():
    subject, html = _render()
    assert "Bom dia, Mateus!" in html
    assert "Padaria do Bairro LTDA" in html
    assert "IRPJ" in html and "R$ 1.000,00" in html
    assert "Simples Nacional" in html and "R$ 250,00" in html
    assert "R$ 1.250,00" in html
    assert subject == "Pagamentos de hoje, 24/09 · Padaria do Bairro LTDA"


def test_email_escapes_document_content():
    """Descriptions are user/AI-authored — they must not become live HTML."""
    _, html = _render(
        company_name="<script>alert(1)</script>",
        payments=[{"label": '<img src=x onerror="steal()">', "category_label": None,
                   "due_date": date(2026, 9, 24), "amount_label": "R$ 1,00"}],
    )
    assert "<script>" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_email_links_to_preview_and_settings():
    _, html = _render()
    assert "https://app.controlladoria.com.br/?pagamentos=previa" in html
    assert "https://app.controlladoria.com.br/account/notifications" in html


def test_weekly_email_shows_dates():
    _, html = _render(frequency="weekly", period_label="esta semana (21/09 a 27/09)")
    assert "24/09" in html


# ─── HTTP ENDPOINTS ────────────────────────────────────────────────────────────


@pytest.fixture
def client_ctx():
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from api import app
    from auth.dependencies import get_current_active_user
    from database import Base, Document, DocumentStatus, Organization, OrgMembership, User, get_db

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    db = Session()
    org = Organization(id=1, company_name="Padaria do Bairro LTDA", cnpj="11.222.333/0001-81")
    other_org = Organization(id=2, company_name="Outra Empresa", cnpj="99.888.777/0001-00")
    user = User(id=1, email="gestor@teste.com", password_hash="x", full_name="Gestor Teste",
                company_name="Padaria do Bairro LTDA", cnpj="11.222.333/0001-81",
                is_active=True, active_org_id=1)
    db.add_all([org, other_org, user])
    db.add(OrgMembership(organization_id=1, user_id=1, role="owner"))
    db.commit()

    today = pr.today_brazil()

    def add_doc(data, added, org_id=1):
        db.add(Document(
            file_name="x.json", file_type="manual", file_path="x", user_id=1,
            organization_id=org_id, status=DocumentStatus.COMPLETED,
            extracted_data_json=json.dumps(data),
            upload_date=added.astimezone(UTC).replace(tzinfo=None),
        ))
        db.commit()

    yesterday = datetime.combine(today - timedelta(days=1), datetime.min.time(), tzinfo=pr.BRT).replace(hour=10)
    add_doc(single(1000, today.isoformat(), category="irpj"), yesterday)
    add_doc(single(250, today.isoformat(), category="simples_nacional"), yesterday)
    add_doc(single(777, today.isoformat()), yesterday, org_id=2)  # another company

    def override_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_active_user] = lambda: Session().query(User).get(1)

    with TestClient(app) as client:
        yield client, Session, today

    app.dependency_overrides.clear()


def test_settings_default_to_in_app_on_email_off(client_ctx):
    client, _, _ = client_ctx
    assert client.get("/payment-reminders/settings").json() == {
        "email_enabled": False, "in_app_enabled": True, "frequency": "daily",
    }


def test_settings_round_trip(client_ctx):
    client, Session, _ = client_ctx
    r = client.put("/payment-reminders/settings", json={"email_enabled": True, "frequency": "weekly"})
    assert r.status_code == 200
    assert r.json() == {"email_enabled": True, "in_app_enabled": True, "frequency": "weekly"}

    from database import PaymentReminderSetting
    row = Session().query(PaymentReminderSetting).one()
    assert (row.user_id, row.organization_id) == (1, 1)


def test_changing_frequency_resets_the_sent_marker(client_ctx):
    client, Session, _ = client_ctx
    from database import PaymentReminderSetting

    client.put("/payment-reminders/settings", json={"email_enabled": True})
    s = Session()
    setting = s.query(PaymentReminderSetting).one()
    setting.last_sent_period = "D2026-09-24"
    s.commit()

    client.put("/payment-reminders/settings", json={"frequency": "monthly"})
    assert Session().query(PaymentReminderSetting).one().last_sent_period is None


def test_invalid_frequency_is_rejected(client_ctx):
    client, _, _ = client_ctx
    assert client.put("/payment-reminders/settings", json={"frequency": "hourly"}).status_code == 422


def test_preview_lists_only_this_company(client_ctx):
    client, _, today = client_ctx
    body = client.get("/payment-reminders/preview?frequency=daily").json()

    assert body["count"] == 2
    assert body["total"] == 1250.0
    assert body["total_label"] == "R$ 1.250,00"
    assert body["start_date"] == body["end_date"] == today.isoformat()
    assert [i["label"] for i in body["items"]] == ["IRPJ", "Simples Nacional"]
    assert 777.0 not in [i["amount"] for i in body["items"]]  # the other company's


def test_test_email_sends_to_the_signed_in_user(client_ctx, monkeypatch):
    client, _, _ = client_ctx
    from email_service import email_service

    sent = {}

    async def fake_send(to, subject, html, reply_to=None):
        sent.update(to=to, subject=subject, html=html)
        return True

    monkeypatch.setattr(email_service, "send_email", fake_send)
    r = client.post("/payment-reminders/test-email")

    assert r.json() == {"sent": True, "to": "gestor@teste.com", "count": 2}
    assert sent["to"] == "gestor@teste.com"
    assert "Bom dia, Gestor!" in sent["html"] and "R$ 1.250,00" in sent["html"]
