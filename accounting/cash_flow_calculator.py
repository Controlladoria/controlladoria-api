"""
Fluxo de Caixa Calculator

Simple and practical: Saldo Inicial + Entradas - Saídas = Saldo Final.
No CPC 03 overhead — just real cash movement.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Dict
from sqlalchemy.orm import Session

from database import Document, DocumentStatus


@dataclass
class CashFlowSection:
    """Seção do Fluxo de Caixa"""
    section_name: str
    line_items: Dict[str, Decimal]
    total: Decimal


@dataclass
class CashFlow:
    """Fluxo de Caixa"""

    company_name: str
    cnpj: str
    period_type: str
    start_date: date
    end_date: date
    method: str

    # Sections (kept for API backward compat — operating = entradas/saídas)
    operating_activities: CashFlowSection
    investing_activities: CashFlowSection
    financing_activities: CashFlowSection

    # Totals
    net_cash_from_operations: Decimal
    net_cash_from_investments: Decimal
    net_cash_from_financing: Decimal
    net_increase_in_cash: Decimal

    # Cash position
    cash_beginning: Decimal
    cash_ending: Decimal


class CashFlowCalculator:
    """
    Fluxo de Caixa: Saldo Inicial + Entradas - Saídas = Saldo Final.

    Cash balance = Initial Balance + cumulative (Income - Expenses).
    All recorded transactions are treated as actual cash movements.
    """

    def __init__(self, db: Session, user_id: int, org_id: Optional[int] = None):
        self.db = db
        self.user_id = user_id
        self.org_id = org_id

    def calculate_cash_flow(
        self,
        period_type: str,
        start_date: date,
        end_date: date,
        method: str = "indirect",
        company_name: str = None,
        cnpj: str = None,
    ) -> CashFlow:
        """Calculate cash flow: Entradas, Saídas, Saldo."""
        from accounting import is_income_type
        from accounting.categories import DRE_CATEGORIES, DRELineType, resolve_category_name

        # Non-cash categories — excluded from cash flow entirely
        NON_CASH_CATEGORIES = {"depreciacao"}

        transactions = self._get_transactions(start_date, end_date)

        # Split into entradas and saídas with category detail
        # Cash flow = actual money movement. Entradas = money IN. Saídas = money OUT.
        # Deductions (taxes, refunds) are money OUT — they go to Saídas, not negative Entradas.
        entradas_by_cat: Dict[str, Decimal] = {}
        saidas_by_cat: Dict[str, Decimal] = {}
        total_entradas = Decimal("0")
        total_saidas = Decimal("0")

        for txn in transactions:
            amount = Decimal(str(txn.get("amount", 0) or 0))
            raw_category = txn.get("category", "nao_categorizado") or "nao_categorizado"
            resolved_category = resolve_category_name(raw_category)
            txn_type = txn.get("transaction_type", "")

            # Skip non-cash items (depreciation doesn't move cash)
            if resolved_category in NON_CASH_CATEGORIES:
                continue

            if is_income_type(txn_type):
                # Income: positive amounts add to entradas, negative reduce entradas
                total_entradas += amount
                entradas_by_cat[raw_category] = entradas_by_cat.get(raw_category, Decimal("0")) + amount
            else:
                # Expenses: always add absolute value to total.
                # Negative expense amounts (refunds/returns) still represent money movement.
                # Line items preserve the original sign for display.
                total_saidas += abs(amount)
                saidas_by_cat[raw_category] = saidas_by_cat.get(raw_category, Decimal("0")) + amount

        # Build readable line items (top categories)
        entradas_items = {
            self._format_category(k): v
            for k, v in sorted(entradas_by_cat.items(), key=lambda x: -x[1])
            if v != 0
        }
        saidas_items = {
            self._format_category(k): -v if v > 0 else v
            for k, v in sorted(saidas_by_cat.items(), key=lambda x: -abs(x[1]))
            if v != 0
        }

        # Cash position
        net_change = total_entradas - total_saidas
        cash_beginning = self._get_cash_balance(start_date)
        cash_ending = cash_beginning + net_change

        # Pack into the CashFlow structure
        # operating = entradas, investing = saídas, financing = empty (backward compat)
        return CashFlow(
            company_name=company_name or "Empresa",
            cnpj=cnpj or "",
            period_type=period_type,
            start_date=start_date,
            end_date=end_date,
            method=method,
            operating_activities=CashFlowSection(
                section_name="Entradas",
                line_items=entradas_items,
                total=total_entradas,
            ),
            investing_activities=CashFlowSection(
                section_name="Saídas",
                line_items=saidas_items,
                total=-total_saidas,
            ),
            financing_activities=CashFlowSection(
                section_name="Resumo",
                line_items={},
                total=Decimal("0"),
            ),
            net_cash_from_operations=total_entradas,
            net_cash_from_investments=-total_saidas,
            net_cash_from_financing=Decimal("0"),
            net_increase_in_cash=net_change,
            cash_beginning=cash_beginning,
            cash_ending=cash_ending,
        )

    def _format_category(self, category: str) -> str:
        """Convert category key to readable label."""
        from accounting.categories import DRE_CATEGORIES
        cat_info = DRE_CATEGORIES.get(category)
        if cat_info:
            return cat_info.get("display_name", category)
        # Clean up raw category names
        return category.replace("_", " ").title()

    def _get_all_transactions(self) -> List[dict]:
        """Get ALL transactions from completed documents."""
        from models import FinancialDocument as FinancialDocumentModel
        from sqlalchemy import or_

        doc_filter = [
            Document.status == DocumentStatus.COMPLETED,
            Document.extracted_data_json.isnot(None),
        ]
        if self.org_id:
            doc_filter.append(or_(
                Document.organization_id == self.org_id,
                (Document.organization_id.is_(None)) & (Document.user_id == self.user_id),
            ))
        else:
            doc_filter.append(Document.user_id == self.user_id)

        documents = self.db.query(Document).filter(*doc_filter).all()

        transactions = []
        for doc in documents:
            try:
                data_dict = json.loads(doc.extracted_data_json)
                extracted = FinancialDocumentModel(**data_dict)

                inner_txns = data_dict.get("transactions")
                if inner_txns and isinstance(inner_txns, list) and len(inner_txns) > 0:
                    for txn in inner_txns:
                        amount = txn.get("amount", 0)
                        if amount is None:
                            amount = 0
                        transactions.append({
                            "date": txn.get("date"),
                            "amount": amount,
                            "category": txn.get("category") or "uncategorized",
                            "transaction_type": txn.get("transaction_type") or extracted.transaction_type,
                            "description": txn.get("description") or "",
                            "document_id": doc.id,
                        })
                else:
                    transactions.append({
                        "date": extracted.issue_date,
                        "amount": extracted.total_amount,
                        "category": extracted.category or "uncategorized",
                        "transaction_type": extracted.transaction_type,
                        "description": extracted.document_number or "",
                        "document_id": doc.id,
                    })
            except Exception:
                continue

        return transactions

    def _get_transactions(self, start_date: date, end_date: date) -> List[dict]:
        """Get transactions within a date range."""
        all_transactions = self._get_all_transactions()

        filtered = []
        for txn in all_transactions:
            t_date = txn.get("date")
            if t_date is None:
                continue
            if isinstance(t_date, str):
                try:
                    t_date = datetime.fromisoformat(t_date).date()
                except (ValueError, TypeError):
                    continue
            elif isinstance(t_date, datetime):
                t_date = t_date.date()
            if start_date <= t_date <= end_date:
                filtered.append(txn)

        return filtered

    def _get_cash_balance(self, reference_date: date) -> Decimal:
        """
        Cash balance BEFORE a date = Initial Balance + cumulative (Income - Expenses)
        for all transactions strictly before the reference_date.
        """
        from accounting import is_income_type
        from accounting.categories import resolve_category_name

        # Get transactions BEFORE the reference date (exclusive)
        day_before = reference_date - timedelta(days=1)
        transactions = self._get_transactions(date(2000, 1, 1), day_before)

        NON_CASH = {"depreciacao"}

        balance = Decimal("0")
        for txn in transactions:
            resolved = resolve_category_name(txn.get("category", "") or "")
            if resolved in NON_CASH:
                continue
            amount = Decimal(str(txn.get("amount", 0) or 0))
            if is_income_type(txn.get("transaction_type", "")):
                balance += amount
            else:
                balance -= abs(amount)  # Always subtract absolute value for expenses

        # Add initial balance from org questionnaire
        initial = self._get_initial_balance(reference_date)
        if initial:
            balance += Decimal(str(initial.cash_and_equivalents or 0))
            if initial.bank_account_balances:
                for entry in initial.bank_account_balances:
                    balance += Decimal(str(entry.get("balance", 0)))

        return balance

    def _get_initial_balance(self, reference_date: date):
        """Load the most recent completed initial balance record."""
        if not self.org_id:
            return None

        from database import OrgInitialBalance

        return (
            self.db.query(OrgInitialBalance)
            .filter(
                OrgInitialBalance.organization_id == self.org_id,
                OrgInitialBalance.is_completed == True,
                OrgInitialBalance.reference_date <= reference_date,
            )
            .order_by(OrgInitialBalance.reference_date.desc())
            .first()
        )
