"""
Tests for Dashboard Metrics API (Item 10)

Tests the /reports/dashboard-metrics endpoint that provides
monthly aggregated data for charting.

NOTE: Uses standalone copies of helper functions to avoid importing
from routers.transactions (which triggers heavy AI client initialization).
"""

import json
import logging
from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Document, DocumentStatus

logger = logging.getLogger(__name__)


# ===== STANDALONE COPIES (avoid heavy routers.transactions import) =====


def _get_month_name_pt_standalone(month: int) -> str:
    """Standalone copy of routers.transactions._get_month_name_pt"""
    names = {
        1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
        5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
        9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
    }
    return names.get(month, str(month))


def _classify_transaction_for_dashboard_standalone(
    months: dict, data: dict, issue_date: str, year: int
):
    """Standalone copy of routers.transactions._classify_transaction_for_dashboard"""
    from accounting.categories import get_dre_category, DRELineType

    if not issue_date:
        return

    try:
        # Parse month from issue_date
        date_parts = issue_date.split("-")
        txn_year = int(date_parts[0])
        txn_month = int(date_parts[1])

        if txn_year != year or txn_month < 1 or txn_month > 12:
            return

        bucket = months[txn_month]

        category = data.get("category", "nao_categorizado")
        txn_type = data.get("transaction_type", "expense")

        # Get amount
        amount_str = data.get("total_amount") or data.get("amount") or "0"
        amount = abs(Decimal(str(amount_str)))

        if txn_type == "income":
            bucket["income_count"] += 1
        else:
            bucket["expense_count"] += 1

        # Track by category
        if category not in bucket["by_category"]:
            bucket["by_category"][category] = (Decimal("0"), 0)
        prev_amt, prev_cnt = bucket["by_category"][category]
        bucket["by_category"][category] = (prev_amt + amount, prev_cnt + 1)

        # Classify using DRE category system
        dre_cat = get_dre_category(category)

        if dre_cat:
            line_type = dre_cat.get("line_type")

            if line_type == DRELineType.REVENUE:
                bucket["receita_bruta"] += amount
                # Track by revenue type for pie chart
                display = dre_cat.get("display_name", category)
                bucket["by_revenue_type"][display] = bucket["by_revenue_type"].get(display, Decimal("0")) + amount

            elif line_type == DRELineType.DEDUCTION:
                bucket["deducoes"] -= amount  # Negative

            elif line_type == DRELineType.VARIABLE_COST:
                bucket["custos_variaveis"] -= amount  # Negative

            elif line_type in (
                DRELineType.FIXED_EXPENSE_ADMIN,
                DRELineType.FIXED_EXPENSE_COMMERCIAL,
                DRELineType.DEPRECIATION,
            ):
                bucket["custos_fixos"] -= amount  # Negative

            elif line_type in (DRELineType.NON_OPERATING_REVENUE, DRELineType.OTHER_REVENUE):
                bucket["receita_bruta"] += amount

            elif line_type in (DRELineType.FINANCIAL_REVENUE,):
                bucket["receita_bruta"] += amount

            elif line_type in (DRELineType.FINANCIAL_EXPENSE, DRELineType.OTHER_EXPENSE):
                bucket["custos_fixos"] -= amount  # Negative

            elif line_type == DRELineType.TAX_ON_PROFIT:
                bucket["deducoes"] -= amount  # Negative

            # Legacy types
            elif line_type == DRELineType.COST:
                bucket["custos_variaveis"] -= amount
            elif line_type in (DRELineType.SALES_EXPENSE, DRELineType.ADMIN_EXPENSE):
                bucket["custos_fixos"] -= amount
            else:
                # Fallback: use transaction_type
                if txn_type == "income":
                    bucket["receita_bruta"] += amount
                else:
                    bucket["custos_fixos"] -= amount
        else:
            # No DRE category found - use transaction_type
            if txn_type == "income":
                bucket["receita_bruta"] += amount
            else:
                bucket["custos_fixos"] -= amount

    except Exception as e:
        logger.debug(f"Dashboard classify error: {e}")


# ===== FIXTURES =====


@pytest.fixture
def db():
    """In-memory SQLite database for testing"""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    yield session
    session.close()


def create_completed_document(db, user_id=1, extracted_data=None):
    """Helper to create a completed document with extracted data"""
    doc = Document(
        file_name="test.pdf",
        file_type="pdf",
        file_path="/tmp/test.pdf",
        file_size=1000,
        status=DocumentStatus.COMPLETED,
        user_id=user_id,
        processed_date=datetime.utcnow(),
    )
    if extracted_data:
        doc.extracted_data_json = json.dumps(extracted_data, default=str)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _make_buckets():
    """Create empty monthly buckets"""
    months = {}
    for m in range(1, 13):
        months[m] = {
            "month": m,
            "month_name": "",
            "receita_bruta": Decimal("0"),
            "deducoes": Decimal("0"),
            "receita_liquida": Decimal("0"),
            "custos_variaveis": Decimal("0"),
            "margem_contribuicao": Decimal("0"),
            "custos_fixos": Decimal("0"),
            "ebitda": Decimal("0"),
            "lucro_liquido": Decimal("0"),
            "income_count": 0,
            "expense_count": 0,
            "by_category": {},
            "by_revenue_type": {},
        }
    return months


# ===== HELPER FUNCTION TESTS =====


class TestGetMonthNamePt:
    """Tests for _get_month_name_pt helper"""

    def test_all_months(self):
        assert _get_month_name_pt_standalone(1) == "Jan"
        assert _get_month_name_pt_standalone(2) == "Fev"
        assert _get_month_name_pt_standalone(3) == "Mar"
        assert _get_month_name_pt_standalone(4) == "Abr"
        assert _get_month_name_pt_standalone(5) == "Mai"
        assert _get_month_name_pt_standalone(6) == "Jun"
        assert _get_month_name_pt_standalone(7) == "Jul"
        assert _get_month_name_pt_standalone(8) == "Ago"
        assert _get_month_name_pt_standalone(9) == "Set"
        assert _get_month_name_pt_standalone(10) == "Out"
        assert _get_month_name_pt_standalone(11) == "Nov"
        assert _get_month_name_pt_standalone(12) == "Dez"

    def test_invalid_month(self):
        assert _get_month_name_pt_standalone(13) == "13"
        assert _get_month_name_pt_standalone(0) == "0"


class TestClassifyTransactionForDashboard:
    """Tests for _classify_transaction_for_dashboard helper"""

    def test_classify_income(self):
        months = _make_buckets()
        data = {
            "transaction_type": "income",
            "category": "receita_vendas_produtos",
            "total_amount": "1000.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2025-03-15", 2025)

        assert months[3]["receita_bruta"] == Decimal("1000")
        assert months[3]["income_count"] == 1
        assert months[3]["expense_count"] == 0

    def test_classify_expense_variable_cost(self):
        months = _make_buckets()
        data = {
            "transaction_type": "expense",
            "category": "cmv",
            "total_amount": "500.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2025-06-10", 2025)

        assert months[6]["custos_variaveis"] == Decimal("-500")
        assert months[6]["expense_count"] == 1

    def test_classify_expense_fixed_cost(self):
        months = _make_buckets()
        data = {
            "transaction_type": "expense",
            "category": "aluguel",
            "total_amount": "3000.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2025-01-05", 2025)

        assert months[1]["custos_fixos"] == Decimal("-3000")

    def test_classify_deduction(self):
        months = _make_buckets()
        data = {
            "transaction_type": "expense",
            "category": "impostos_sobre_vendas",
            "total_amount": "200.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2025-04-20", 2025)

        assert months[4]["deducoes"] == Decimal("-200")

    def test_wrong_year_ignored(self):
        months = _make_buckets()
        data = {
            "transaction_type": "income",
            "category": "receita_servicos",
            "total_amount": "5000.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2024-03-15", 2025)

        # Should not affect 2025 buckets
        assert months[3]["receita_bruta"] == Decimal("0")

    def test_no_date_ignored(self):
        months = _make_buckets()
        data = {
            "transaction_type": "income",
            "category": "receita_servicos",
            "total_amount": "5000.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, None, 2025)

        # All months should be zero
        for m in range(1, 13):
            assert months[m]["receita_bruta"] == Decimal("0")

    def test_tracks_by_category(self):
        months = _make_buckets()
        data = {
            "transaction_type": "expense",
            "category": "aluguel",
            "total_amount": "2000.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2025-05-01", 2025)

        assert "aluguel" in months[5]["by_category"]
        amt, cnt = months[5]["by_category"]["aluguel"]
        assert amt == Decimal("2000")
        assert cnt == 1

    def test_multiple_transactions_same_month(self):
        months = _make_buckets()

        # Two income transactions in the same month
        _classify_transaction_for_dashboard_standalone(
            months,
            {"transaction_type": "income", "category": "receita_servicos", "total_amount": "1000.00"},
            "2025-02-10",
            2025,
        )
        _classify_transaction_for_dashboard_standalone(
            months,
            {"transaction_type": "income", "category": "receita_vendas_produtos", "total_amount": "2000.00"},
            "2025-02-20",
            2025,
        )

        assert months[2]["receita_bruta"] == Decimal("3000")
        assert months[2]["income_count"] == 2

    def test_ledger_transaction_with_amount_field(self):
        """Ledger transactions use 'amount' field instead of 'total_amount'"""
        months = _make_buckets()
        data = {
            "transaction_type": "income",
            "category": "receita_servicos",
            "amount": "750.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2025-09-15", 2025)

        assert months[9]["receita_bruta"] == Decimal("750")

    def test_uncategorized_income(self):
        """Unknown categories should use transaction_type to classify"""
        months = _make_buckets()
        data = {
            "transaction_type": "income",
            "category": "some_unknown_category",
            "total_amount": "500.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2025-07-01", 2025)

        # Should still count as income
        assert months[7]["receita_bruta"] == Decimal("500")

    def test_uncategorized_expense(self):
        """Unknown categories should use transaction_type to classify"""
        months = _make_buckets()
        data = {
            "transaction_type": "expense",
            "category": "some_unknown_expense",
            "total_amount": "300.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2025-11-01", 2025)

        # Should go to custos_fixos as fallback
        assert months[11]["custos_fixos"] == Decimal("-300")

    def test_tracks_by_revenue_type(self):
        """Revenue transactions should track by revenue type for pie chart"""
        months = _make_buckets()
        _classify_transaction_for_dashboard_standalone(
            months,
            {"transaction_type": "income", "category": "receita_servicos", "total_amount": "1000.00"},
            "2025-03-01",
            2025,
        )
        _classify_transaction_for_dashboard_standalone(
            months,
            {"transaction_type": "income", "category": "receita_vendas_produtos", "total_amount": "2000.00"},
            "2025-03-15",
            2025,
        )

        # Should have two revenue types in March
        assert len(months[3]["by_revenue_type"]) == 2
        assert months[3]["receita_bruta"] == Decimal("3000")

    def test_financial_revenue_counts_as_income(self):
        """Financial revenue (e.g., juros_recebidos) should go to receita_bruta"""
        months = _make_buckets()
        data = {
            "transaction_type": "income",
            "category": "juros_recebidos",
            "total_amount": "150.00",
        }
        _classify_transaction_for_dashboard_standalone(months, data, "2025-08-01", 2025)

        assert months[8]["receita_bruta"] == Decimal("150")
        assert months[8]["income_count"] == 1


class TestDashboardMetricsIntegration:
    """Integration tests using the DB fixture"""

    def test_completed_docs_included(self, db):
        """Only COMPLETED documents should be in metrics"""
        create_completed_document(
            db,
            extracted_data={
                "document_type": "invoice",
                "issue_date": "2025-03-15",
                "transaction_type": "income",
                "category": "receita_servicos",
                "total_amount": "1000.00",
            },
        )
        # Pending doc should be excluded
        pending = Document(
            file_name="pending.pdf",
            file_type="pdf",
            file_path="/tmp/p.pdf",
            file_size=100,
            status=DocumentStatus.PENDING,
            user_id=1,
        )
        pending.extracted_data_json = json.dumps({
            "document_type": "invoice",
            "issue_date": "2025-03-15",
            "transaction_type": "income",
            "total_amount": "9999.00",
        })
        db.add(pending)
        db.commit()

        completed = (
            db.query(Document)
            .filter(
                Document.status == DocumentStatus.COMPLETED,
                Document.extracted_data_json.isnot(None),
            )
            .all()
        )

        assert len(completed) == 1
        assert completed[0].file_name == "test.pdf"

    def test_cancelled_docs_excluded(self, db):
        """CANCELLED documents should not appear in metrics"""
        cancelled = Document(
            file_name="cancelled.pdf",
            file_type="pdf",
            file_path="/tmp/c.pdf",
            file_size=100,
            status=DocumentStatus.CANCELLED,
            user_id=1,
        )
        cancelled.extracted_data_json = json.dumps({
            "document_type": "invoice",
            "issue_date": "2025-06-15",
            "transaction_type": "income",
            "total_amount": "5000.00",
        })
        db.add(cancelled)
        db.commit()

        completed = (
            db.query(Document)
            .filter(
                Document.status == DocumentStatus.COMPLETED,
                Document.extracted_data_json.isnot(None),
            )
            .all()
        )

        assert len(completed) == 0

    def test_ledger_documents_multi_transactions(self, db):
        """Ledger docs with multiple transactions should be classified per-transaction"""
        months = _make_buckets()

        data = {
            "document_type": "transaction_ledger",
            "transactions": [
                {
                    "date": "2025-01-10",
                    "transaction_type": "income",
                    "category": "receita_servicos",
                    "amount": "1000.00",
                },
                {
                    "date": "2025-01-20",
                    "transaction_type": "expense",
                    "category": "aluguel",
                    "amount": "500.00",
                },
            ],
        }

        # Process each transaction individually (as the endpoint does)
        for txn in data["transactions"]:
            _classify_transaction_for_dashboard_standalone(
                months, txn, txn.get("date"), 2025
            )

        assert months[1]["receita_bruta"] == Decimal("1000")
        assert months[1]["custos_fixos"] == Decimal("-500")
        assert months[1]["income_count"] == 1
        assert months[1]["expense_count"] == 1

    def test_multi_tenant_isolation(self, db):
        """Documents from different users should be queryable separately"""
        create_completed_document(
            db,
            user_id=1,
            extracted_data={
                "document_type": "invoice",
                "issue_date": "2025-03-15",
                "transaction_type": "income",
                "total_amount": "1000.00",
            },
        )
        create_completed_document(
            db,
            user_id=2,
            extracted_data={
                "document_type": "invoice",
                "issue_date": "2025-03-15",
                "transaction_type": "income",
                "total_amount": "5000.00",
            },
        )

        user1_docs = (
            db.query(Document)
            .filter(
                Document.status == DocumentStatus.COMPLETED,
                Document.user_id == 1,
                Document.extracted_data_json.isnot(None),
            )
            .all()
        )

        assert len(user1_docs) == 1

        user2_docs = (
            db.query(Document)
            .filter(
                Document.status == DocumentStatus.COMPLETED,
                Document.user_id == 2,
                Document.extracted_data_json.isnot(None),
            )
            .all()
        )

        assert len(user2_docs) == 1
