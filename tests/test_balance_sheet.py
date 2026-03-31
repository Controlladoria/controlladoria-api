"""
Tests for Balance Sheet (Balanço Patrimonial) functionality
Tests double-entry bookkeeping, chart of accounts, and balance sheet calculation
"""

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from accounting.accounting_engine import AccountingEngine
from accounting.balance_sheet_calculator import BalanceSheet, BalanceSheetCalculator
from accounting.balance_sheet_exports import (
    export_balance_sheet_to_csv,
    export_balance_sheet_to_excel,
    export_balance_sheet_to_pdf,
)
from accounting.chart_of_accounts import (
    AccountNature,
    AccountType,
    BrazilianChartOfAccounts,
)
from database import Base, ChartOfAccountsEntry, JournalEntry, JournalEntryLine, User


# Test database setup
@pytest.fixture(scope="function")
def db_session():
    """Create a test database session"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    session.close()


@pytest.fixture
def test_user(db_session):
    """Create a test user"""
    user = User(
        email="test@example.com",
        password_hash="hashed",
        full_name="Test User",
        company_name="Test Company LTDA",
        cnpj="12.345.678/0001-90",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_chart_of_accounts(db_session, test_user):
    """Create test chart of accounts"""
    # Create a few essential accounts for testing
    accounts_to_create = [
        # Assets
        ("1.01.001", "Caixa", AccountType.ATIVO_CIRCULANTE, AccountNature.DEBIT),
        (
            "1.01.002",
            "Bancos Conta Corrente",
            AccountType.ATIVO_CIRCULANTE,
            AccountNature.DEBIT,
        ),
        ("1.01.003", "Clientes", AccountType.ATIVO_CIRCULANTE, AccountNature.DEBIT),
        ("1.02.001", "Imóveis", AccountType.ATIVO_NAO_CIRCULANTE, AccountNature.DEBIT),
        # Liabilities
        (
            "2.01.001",
            "Fornecedores",
            AccountType.PASSIVO_CIRCULANTE,
            AccountNature.CREDIT,
        ),
        (
            "2.01.002",
            "Impostos a Recolher",
            AccountType.PASSIVO_CIRCULANTE,
            AccountNature.CREDIT,
        ),
        (
            "2.02.001",
            "Empréstimos de Longo Prazo",
            AccountType.PASSIVO_NAO_CIRCULANTE,
            AccountNature.CREDIT,
        ),
        # Equity
        (
            "3.01.001",
            "Capital Social",
            AccountType.PATRIMONIO_LIQUIDO,
            AccountNature.CREDIT,
        ),
        (
            "3.02.001",
            "Lucros Acumulados",
            AccountType.PATRIMONIO_LIQUIDO,
            AccountNature.CREDIT,
        ),
        # Revenue
        ("4.01.001", "Receita de Vendas", AccountType.RECEITA, AccountNature.CREDIT),
        # Expenses
        (
            "5.01.001",
            "Custo das Mercadorias Vendidas",
            AccountType.DESPESA,
            AccountNature.DEBIT,
        ),
        ("5.02.001", "Salários", AccountType.DESPESA, AccountNature.DEBIT),
    ]

    for code, name, acc_type, nature in accounts_to_create:
        account = ChartOfAccountsEntry(
            user_id=test_user.id,
            account_code=code,
            account_name=name,
            account_type=acc_type.value,
            account_nature=nature.value,
            is_active=True,
            is_system_account=True,
            current_balance=0,
        )
        db_session.add(account)

    db_session.commit()

    return (
        db_session.query(ChartOfAccountsEntry)
        .filter(ChartOfAccountsEntry.user_id == test_user.id)
        .all()
    )


# ===== CHART OF ACCOUNTS TESTS =====


def test_brazilian_chart_of_accounts_structure():
    """Test that Brazilian chart of accounts has correct structure"""
    chart = BrazilianChartOfAccounts()

    # Should have multiple accounts
    assert len(chart.get_all_accounts()) > 50

    # Should have all account types
    asset_accounts = chart.get_accounts_by_type(AccountType.ATIVO_CIRCULANTE)
    assert len(asset_accounts) > 0

    liability_accounts = chart.get_accounts_by_type(AccountType.PASSIVO_CIRCULANTE)
    assert len(liability_accounts) > 0

    equity_accounts = chart.get_accounts_by_type(AccountType.PATRIMONIO_LIQUIDO)
    assert len(equity_accounts) > 0


def test_account_search():
    """Test account search functionality"""
    chart = BrazilianChartOfAccounts()

    # Search for "Caixa"
    results = chart.search_accounts("Caixa")
    assert len(results) > 0
    assert any("Caixa" in acc["name"] for acc in results)


def test_get_account_by_code():
    """Test getting account by code"""
    chart = BrazilianChartOfAccounts()

    # Get Caixa account
    account = chart.get_account("1.01.001")
    assert account is not None
    assert account["name"] == "Caixa"
    assert account["type"] == AccountType.ATIVO_CIRCULANTE
    assert account["nature"] == AccountNature.DEBIT


# ===== ACCOUNTING ENGINE TESTS =====


def test_accounting_engine_initialization(db_session, test_user):
    """Test AccountingEngine initialization"""
    engine = AccountingEngine(db_session, test_user.id)
    assert engine.db == db_session
    assert engine.user_id == test_user.id


def test_create_opening_balances(db_session, test_user, test_chart_of_accounts):
    """Test setting opening balances"""
    engine = AccountingEngine(db_session, test_user.id)

    opening_balances = {
        "1.01.001": 5000.00,  # Caixa
        "3.01.001": 5000.00,  # Capital Social
    }

    entry = engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    # Should create 1 journal entry with 2 lines (plus balancing entry)
    assert entry is not None
    assert len(entry.lines) >= 2

    # Verify balances
    caixa = (
        db_session.query(ChartOfAccountsEntry)
        .filter_by(user_id=test_user.id, account_code="1.01.001")
        .first()
    )

    # Balance should be updated (500000 cents = R$ 5,000)
    assert caixa.current_balance == 500000


def test_create_manual_journal_entry(db_session, test_user, test_chart_of_accounts):
    """Test creating manual journal entry"""
    engine = AccountingEngine(db_session, test_user.id)

    # Create a sale entry: Debit Cash, Credit Revenue
    lines = [
        {
            "account_code": "1.01.001",  # Caixa
            "debit_amount": 1000,
            "credit_amount": 0,
            "description": "Cash received",
        },
        {
            "account_code": "4.01.001",  # Receita de Vendas
            "debit_amount": 0,
            "credit_amount": 1000,
            "description": "Sales revenue",
        },
    ]

    entry = engine.create_manual_journal_entry(
        entry_date=datetime(2024, 6, 15),
        description="Sale of merchandise",
        lines=lines,
        created_by="test@example.com",
    )

    # Verify entry created
    assert entry.id is not None
    assert entry.description == "Sale of merchandise"
    assert len(entry.lines) == 2

    # Verify entry balances (debits = credits)
    total_debits = sum(line.debit_amount for line in entry.lines)
    total_credits = sum(line.credit_amount for line in entry.lines)
    assert total_debits == total_credits == 1000


def test_journal_entry_validation_unbalanced(
    db_session, test_user, test_chart_of_accounts
):
    """Test that unbalanced journal entries are rejected"""
    engine = AccountingEngine(db_session, test_user.id)

    # Create unbalanced entry
    lines = [
        {"account_code": "1.01.001", "debit_amount": 1000, "credit_amount": 0},
        {
            "account_code": "4.01.001",
            "debit_amount": 0,
            "credit_amount": 500,  # Doesn't balance!
        },
    ]

    with pytest.raises(ValueError, match="not balance"):
        engine.create_manual_journal_entry(
            entry_date=datetime(2024, 6, 15),
            description="Unbalanced entry",
            lines=lines,
            created_by="test@example.com",
        )


def test_generate_journal_entry_from_transaction(
    db_session, test_user, test_chart_of_accounts
):
    """Test automatic journal entry generation from transaction"""
    engine = AccountingEngine(db_session, test_user.id)

    # Transaction data (simulating what comes from document processing)
    transaction = {
        "date": datetime(2024, 6, 15),
        "amount": 1500.00,
        "category": "sales",
        "transaction_type": "income",
        "description": "Sale to customer",
    }

    entry = engine.generate_journal_entry_from_transaction(
        transaction_data=transaction, created_by="system"
    )

    # Verify entry created
    assert entry.id is not None
    assert entry.source_type == "automatic"

    # Should have 2 lines (debit cash, credit revenue)
    assert len(entry.lines) == 2

    # Verify balances
    total_debits = sum(line.debit_amount for line in entry.lines)
    total_credits = sum(line.credit_amount for line in entry.lines)
    assert total_debits == total_credits


# ===== BALANCE SHEET CALCULATOR TESTS =====


def test_balance_sheet_calculator_initialization(db_session, test_user):
    """Test BalanceSheetCalculator initialization"""
    calculator = BalanceSheetCalculator(db_session, test_user.id)
    assert calculator.db == db_session
    assert calculator.user_id == test_user.id


def test_calculate_simple_balance_sheet(db_session, test_user, test_chart_of_accounts):
    """Test calculating a simple balance sheet"""
    engine = AccountingEngine(db_session, test_user.id)

    # Set up opening balances
    opening_balances = {
        "1.01.001": 10000.00,  # Caixa (Asset)
        "2.01.001": 3000.00,  # Fornecedores (Liability)
        "3.01.001": 7000.00,  # Capital Social (Equity)
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    # Calculate balance sheet
    calculator = BalanceSheetCalculator(db_session, test_user.id)
    balance_sheet = calculator.calculate_balance_sheet(
        reference_date=date(2024, 1, 1),
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
    )

    # Verify structure
    assert isinstance(balance_sheet, BalanceSheet)
    assert balance_sheet.reference_date == date(2024, 1, 31)  # Expanded to end-of-month
    assert balance_sheet.company_name == "Test Company"

    # Verify balances
    assert balance_sheet.ativo_circulante == Decimal("10000.00")
    assert balance_sheet.passivo_circulante == Decimal("3000.00")
    assert balance_sheet.patrimonio_liquido == Decimal("7000.00")
    assert balance_sheet.total_ativo == Decimal("10000.00")

    # Verify balance equation: Assets = Liabilities + Equity
    assert balance_sheet.is_balanced


def test_balance_sheet_with_transactions(db_session, test_user, test_chart_of_accounts):
    """Test balance sheet calculation with transactions"""
    engine = AccountingEngine(db_session, test_user.id)

    # Opening balances
    opening_balances = {
        "1.01.001": 5000.00,  # Caixa
        "3.01.001": 5000.00,  # Capital Social
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    # Transaction 1: Sale (increases cash and equity via revenue)
    transaction1 = {
        "date": datetime(2024, 6, 15),
        "amount": 2000.00,
        "category": "sales",
        "transaction_type": "income",
        "description": "Sale to customer",
    }

    engine.generate_journal_entry_from_transaction(
        transaction_data=transaction1, created_by="system"
    )

    # Transaction 2: Expense (decreases cash and equity)
    transaction2 = {
        "date": datetime(2024, 6, 20),
        "amount": 500.00,
        "category": "rent",
        "transaction_type": "expense",
        "description": "Rent payment",
    }

    engine.generate_journal_entry_from_transaction(
        transaction_data=transaction2, created_by="system"
    )

    # Calculate balance sheet as of June 30
    calculator = BalanceSheetCalculator(db_session, test_user.id)
    balance_sheet = calculator.calculate_balance_sheet(reference_date=date(2024, 6, 30))

    # Cash should be: 5000 + 2000 - 500 = 6,500
    assert balance_sheet.ativo_circulante == Decimal("6500.00")

    # Should still be balanced
    assert balance_sheet.is_balanced


def test_get_trial_balance(db_session, test_user, test_chart_of_accounts):
    """Test trial balance (balancete) calculation"""
    engine = AccountingEngine(db_session, test_user.id)

    # Set up balances
    opening_balances = {
        "1.01.001": 10000.00,  # Caixa
        "2.01.001": 3000.00,  # Fornecedores
        "3.01.001": 7000.00,  # Capital Social
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    # Get trial balance
    calculator = BalanceSheetCalculator(db_session, test_user.id)
    trial_balance = calculator.get_trial_balance(date(2024, 1, 1))

    # Should have accounts with balances
    assert len(trial_balance) == 3

    # Calculate totals
    total_debits = sum(item["debit_balance"] for item in trial_balance)
    total_credits = sum(item["credit_balance"] for item in trial_balance)

    # Debits should equal credits
    assert abs(total_debits - total_credits) < 0.01


def test_get_account_ledger(db_session, test_user, test_chart_of_accounts):
    """Test account ledger (razão) generation"""
    engine = AccountingEngine(db_session, test_user.id)

    # Create multiple entries for Caixa
    # Entry 1: Opening balance
    lines1 = [
        {"account_code": "1.01.001", "debit_amount": 5000, "credit_amount": 0},
        {"account_code": "3.01.001", "debit_amount": 0, "credit_amount": 5000},
    ]
    engine.create_manual_journal_entry(
        entry_date=datetime(2024, 1, 1),
        description="Opening balance",
        lines=lines1,
        created_by="test@example.com",
    )

    # Entry 2: Sale
    lines2 = [
        {"account_code": "1.01.001", "debit_amount": 2000, "credit_amount": 0},
        {"account_code": "4.01.001", "debit_amount": 0, "credit_amount": 2000},
    ]
    engine.create_manual_journal_entry(
        entry_date=datetime(2024, 6, 15),
        description="Sale",
        lines=lines2,
        created_by="test@example.com",
    )

    # Entry 3: Payment
    lines3 = [
        {"account_code": "5.02.001", "debit_amount": 500, "credit_amount": 0},
        {"account_code": "1.01.001", "debit_amount": 0, "credit_amount": 500},
    ]
    engine.create_manual_journal_entry(
        entry_date=datetime(2024, 6, 20),
        description="Salary payment",
        lines=lines3,
        created_by="test@example.com",
    )

    # Get Caixa ledger
    calculator = BalanceSheetCalculator(db_session, test_user.id)
    ledger = calculator.get_account_ledger("1.01.001")

    # Should have 3 entries
    assert len(ledger) == 3

    # Verify running balance
    assert ledger[0]["balance"] == 50.00  # R$ 50 from 5000 cents
    assert ledger[1]["balance"] == 70.00  # R$ 70 (50 + 20)
    assert ledger[2]["balance"] == 65.00  # R$ 65 (70 - 5)


# ===== EXPORT TESTS =====


def test_export_balance_sheet_to_pdf(db_session, test_user, test_chart_of_accounts):
    """Test Balance Sheet PDF export"""
    engine = AccountingEngine(db_session, test_user.id)

    # Set up simple balance sheet
    opening_balances = {
        "1.01.001": 10000.00,
        "3.01.001": 10000.00,
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    # Calculate and export
    calculator = BalanceSheetCalculator(db_session, test_user.id)
    balance_sheet = calculator.calculate_balance_sheet(
        reference_date=date(2024, 1, 1),
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
    )

    pdf_bytes = export_balance_sheet_to_pdf(balance_sheet)

    # Verify PDF was generated
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")  # PDF magic number


def test_export_balance_sheet_to_excel(db_session, test_user, test_chart_of_accounts):
    """Test Balance Sheet Excel export"""
    engine = AccountingEngine(db_session, test_user.id)

    opening_balances = {
        "1.01.001": 10000.00,
        "3.01.001": 10000.00,
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    calculator = BalanceSheetCalculator(db_session, test_user.id)
    balance_sheet = calculator.calculate_balance_sheet(
        reference_date=date(2024, 1, 1),
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
    )

    excel_bytes = export_balance_sheet_to_excel(balance_sheet)

    # Verify Excel was generated
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0


def test_export_balance_sheet_to_csv(db_session, test_user, test_chart_of_accounts):
    """Test Balance Sheet CSV export"""
    engine = AccountingEngine(db_session, test_user.id)

    opening_balances = {
        "1.01.001": 10000.00,
        "3.01.001": 10000.00,
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    calculator = BalanceSheetCalculator(db_session, test_user.id)
    balance_sheet = calculator.calculate_balance_sheet(
        reference_date=date(2024, 1, 1),
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
    )

    csv_string = export_balance_sheet_to_csv(balance_sheet)

    # Verify CSV was generated
    assert isinstance(csv_string, str)
    assert len(csv_string) > 0
    assert "GERENCIAL" in csv_string  # CSV header uses "BALANÇO GERENCIAL"
    assert "ATIVO" in csv_string
    assert "PASSIVO" in csv_string


def test_balance_sheet_to_dict(db_session, test_user, test_chart_of_accounts):
    """Test Balance Sheet to_dict() method for JSON serialization"""
    engine = AccountingEngine(db_session, test_user.id)

    opening_balances = {
        "1.01.001": 10000.00,
        "2.01.001": 3000.00,
        "3.01.001": 7000.00,
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    calculator = BalanceSheetCalculator(db_session, test_user.id)
    balance_sheet = calculator.calculate_balance_sheet(
        reference_date=date(2024, 1, 1),
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
    )

    # Convert to dict
    bs_dict = balance_sheet.to_dict()

    # Verify structure
    assert "reference_date" in bs_dict
    assert "company_name" in bs_dict
    assert "ativo" in bs_dict
    assert "passivo" in bs_dict
    assert "patrimonio_liquido" in bs_dict
    assert "is_balanced" in bs_dict

    # Verify values are floats (JSON-serializable)
    assert isinstance(bs_dict["ativo"]["total"], float)
    assert isinstance(bs_dict["passivo"]["total"], float)
    assert isinstance(bs_dict["patrimonio_liquido"]["total"], float)

    # Verify balance
    assert bs_dict["is_balanced"] is True


# ===== INTEGRATION TESTS =====


def test_complete_accounting_cycle(db_session, test_user, test_chart_of_accounts):
    """Test complete accounting cycle: opening -> transactions -> balance sheet"""
    engine = AccountingEngine(db_session, test_user.id)
    calculator = BalanceSheetCalculator(db_session, test_user.id)

    # Step 1: Opening balances (January 1, 2024)
    opening_balances = {
        "1.01.001": 20000.00,  # Caixa
        "1.02.001": 100000.00,  # Imóveis
        "2.01.001": 10000.00,  # Fornecedores
        "2.02.001": 50000.00,  # Empréstimos LP
        "3.01.001": 60000.00,  # Capital Social
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    # Step 2: June transactions
    # Sale
    engine.generate_journal_entry_from_transaction(
        {
            "date": datetime(2024, 6, 5),
            "amount": 15000.00,
            "category": "sales",
            "transaction_type": "income",
            "description": "June sales",
        },
        created_by="system",
    )

    # Expenses
    engine.generate_journal_entry_from_transaction(
        {
            "date": datetime(2024, 6, 10),
            "amount": 3000.00,
            "category": "salary",
            "transaction_type": "expense",
            "description": "Salaries",
        },
        created_by="system",
    )

    engine.generate_journal_entry_from_transaction(
        {
            "date": datetime(2024, 6, 15),
            "amount": 8000.00,
            "category": "cost_of_goods",
            "transaction_type": "expense",
            "description": "COGS",
        },
        created_by="system",
    )

    # Step 3: Calculate balance sheet as of June 30
    balance_sheet_june = calculator.calculate_balance_sheet(
        reference_date=date(2024, 6, 30),
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
    )

    # Verify balance sheet is balanced
    assert balance_sheet_june.is_balanced

    # Verify cash increased by net income (15000 - 3000 - 8000 = 4000)
    # Cash should be: 20000 + 4000 = 24,000
    assert balance_sheet_june.ativo_circulante == Decimal("24000.00")

    # Fixed assets unchanged
    assert balance_sheet_june.ativo_nao_circulante == Decimal("100000.00")

    # Step 4: Export to all formats
    pdf = export_balance_sheet_to_pdf(balance_sheet_june)
    excel = export_balance_sheet_to_excel(balance_sheet_june)
    csv = export_balance_sheet_to_csv(balance_sheet_june)

    assert len(pdf) > 0
    assert len(excel) > 0
    assert len(csv) > 0

    # Step 5: Verify trial balance
    trial_balance = calculator.get_trial_balance(date(2024, 6, 30))
    total_debits = sum(item["debit_balance"] for item in trial_balance)
    total_credits = sum(item["credit_balance"] for item in trial_balance)

    assert abs(total_debits - total_credits) < 0.01


# ===== V2 BALANCE SHEET TESTS =====


@pytest.fixture
def test_chart_of_accounts_v2(db_session, test_user):
    """Create V2 chart of accounts with Imobilizado and Intangivel accounts"""
    accounts_to_create = [
        # Assets - Circulante
        ("1.01.001", "Caixa", AccountType.ATIVO_CIRCULANTE, AccountNature.DEBIT),
        ("1.01.002", "Bancos Conta Corrente", AccountType.ATIVO_CIRCULANTE, AccountNature.DEBIT),
        ("1.01.003", "Clientes", AccountType.ATIVO_CIRCULANTE, AccountNature.DEBIT),
        # Assets - Nao Circulante (Realizavel LP)
        ("1.02.001", "Créditos a Receber LP", AccountType.ATIVO_NAO_CIRCULANTE, AccountNature.DEBIT),
        ("1.02.010", "Investimentos", AccountType.ATIVO_NAO_CIRCULANTE, AccountNature.DEBIT),
        # Assets - Imobilizado (1.02.02x)
        ("1.02.020", "Imobilizado - Custo", AccountType.ATIVO_NAO_CIRCULANTE, AccountNature.DEBIT),
        # Assets - Intangivel (1.02.03x)
        ("1.02.030", "Intangível - Custo", AccountType.ATIVO_NAO_CIRCULANTE, AccountNature.DEBIT),
        # Liabilities
        ("2.01.001", "Fornecedores", AccountType.PASSIVO_CIRCULANTE, AccountNature.CREDIT),
        ("2.02.001", "Empréstimos LP", AccountType.PASSIVO_NAO_CIRCULANTE, AccountNature.CREDIT),
        # Equity
        ("3.01.001", "Capital Social", AccountType.PATRIMONIO_LIQUIDO, AccountNature.CREDIT),
        # Revenue
        ("4.01.001", "Receita de Vendas", AccountType.RECEITA, AccountNature.CREDIT),
        # Expenses
        ("5.01.001", "CMV", AccountType.DESPESA, AccountNature.DEBIT),
    ]

    for code, name, acc_type, nature in accounts_to_create:
        account = ChartOfAccountsEntry(
            user_id=test_user.id,
            account_code=code,
            account_name=name,
            account_type=acc_type.value,
            account_nature=nature.value,
            is_active=True,
            is_system_account=True,
            current_balance=0,
        )
        db_session.add(account)

    db_session.commit()

    return (
        db_session.query(ChartOfAccountsEntry)
        .filter(ChartOfAccountsEntry.user_id == test_user.id)
        .all()
    )


def test_v2_balance_sheet_4_group_assets(db_session, test_user, test_chart_of_accounts_v2):
    """Test V2 balance sheet with 4 asset groups: Circulante, Nao Circulante, Imobilizado, Intangivel"""
    engine = AccountingEngine(db_session, test_user.id)

    opening_balances = {
        "1.01.001": 10000.00,    # Caixa (Circulante)
        "1.01.002": 5000.00,     # Bancos (Circulante)
        "1.02.001": 20000.00,    # Créditos LP (Nao Circulante)
        "1.02.010": 15000.00,    # Investimentos (Nao Circulante)
        "1.02.020": 70000.00,    # Imobilizado Custo (net of depreciation)
        "1.02.030": 25000.00,    # Intangível Custo (net of amortization)
        "2.01.001": 15000.00,    # Fornecedores
        "2.02.001": 50000.00,    # Empréstimos LP
        "3.01.001": 80000.00,    # Capital Social
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    calculator = BalanceSheetCalculator(db_session, test_user.id)
    bs = calculator.calculate_balance_sheet(
        reference_date=date(2024, 1, 1),
        company_name="V2 Test Company",
    )

    # Verify 4-group breakdown
    assert bs.ativo_circulante == Decimal("15000.00")      # 10000 + 5000
    assert bs.ativo_nao_circulante == Decimal("35000.00")   # 20000 + 15000
    assert bs.imobilizado == Decimal("70000.00")            # Imobilizado group
    assert bs.intangivel == Decimal("25000.00")             # Intangível group

    # Total Ativo = all 4 groups
    assert bs.total_ativo == Decimal("145000.00")

    # Liabilities
    assert bs.passivo_circulante == Decimal("15000.00")
    assert bs.passivo_nao_circulante == Decimal("50000.00")
    assert bs.total_passivo == Decimal("65000.00")

    # Equity
    assert bs.patrimonio_liquido == Decimal("80000.00")

    # Balance check
    assert bs.is_balanced


def test_v2_balance_sheet_line_lists(db_session, test_user, test_chart_of_accounts_v2):
    """Test V2 balance sheet populates separate line lists for each group"""
    engine = AccountingEngine(db_session, test_user.id)

    opening_balances = {
        "1.01.001": 10000.00,
        "1.02.001": 20000.00,
        "1.02.020": 50000.00,
        "1.02.030": 15000.00,
        "3.01.001": 95000.00,
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    calculator = BalanceSheetCalculator(db_session, test_user.id)
    bs = calculator.calculate_balance_sheet(reference_date=date(2024, 1, 1))

    # Circulante lines go in asset_lines
    assert len(bs.asset_lines) == 1
    assert bs.asset_lines[0].code == "1.01.001"

    # Nao Circulante lines go in asset_noncurrent_lines
    assert len(bs.asset_noncurrent_lines) == 1
    assert bs.asset_noncurrent_lines[0].code == "1.02.001"

    # Imobilizado lines go in imobilizado_lines
    assert len(bs.imobilizado_lines) == 1
    assert bs.imobilizado_lines[0].code == "1.02.020"

    # Intangivel lines go in intangivel_lines
    assert len(bs.intangivel_lines) == 1
    assert bs.intangivel_lines[0].code == "1.02.030"


def test_v2_balance_sheet_to_dict_has_imobilizado_intangivel(db_session, test_user, test_chart_of_accounts_v2):
    """Test V2 to_dict() includes imobilizado and intangivel fields"""
    engine = AccountingEngine(db_session, test_user.id)

    opening_balances = {
        "1.01.001": 10000.00,
        "1.02.020": 50000.00,
        "1.02.030": 20000.00,
        "3.01.001": 80000.00,
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    calculator = BalanceSheetCalculator(db_session, test_user.id)
    bs = calculator.calculate_balance_sheet(reference_date=date(2024, 1, 1))

    bs_dict = bs.to_dict()

    # V2: ativo dict should have imobilizado and intangivel
    assert "imobilizado" in bs_dict["ativo"]
    assert "intangivel" in bs_dict["ativo"]
    assert bs_dict["ativo"]["imobilizado"] == 50000.0
    assert bs_dict["ativo"]["intangivel"] == 20000.0
    assert bs_dict["ativo"]["circulante"] == 10000.0
    assert bs_dict["ativo"]["total"] == 80000.0


def test_v2_balance_sheet_exports_with_4_groups(db_session, test_user, test_chart_of_accounts_v2):
    """Test V2 exports work with 4-group structure"""
    engine = AccountingEngine(db_session, test_user.id)

    opening_balances = {
        "1.01.001": 10000.00,
        "1.02.001": 20000.00,
        "1.02.020": 50000.00,
        "1.02.030": 15000.00,
        "2.01.001": 10000.00,
        "2.02.001": 30000.00,
        "3.01.001": 55000.00,
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    calculator = BalanceSheetCalculator(db_session, test_user.id)
    bs = calculator.calculate_balance_sheet(
        reference_date=date(2024, 1, 1),
        company_name="V2 Export Test",
    )

    # PDF export
    pdf_bytes = export_balance_sheet_to_pdf(bs)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF")

    # Excel export
    excel_bytes = export_balance_sheet_to_excel(bs)
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0

    # CSV export
    csv_string = export_balance_sheet_to_csv(bs)
    assert isinstance(csv_string, str)
    assert "Imobilizado" in csv_string
    assert "Intangível" in csv_string
    assert "Ativo Não Circulante" in csv_string
    assert "TOTAL DO ATIVO" in csv_string
    assert "TOTAL DO PASSIVO + PL" in csv_string


def test_v2_balance_sheet_net_income_in_equity(db_session, test_user, test_chart_of_accounts_v2):
    """Test V2: net income from revenue/expenses flows into patrimonio_liquido"""
    engine = AccountingEngine(db_session, test_user.id)

    opening_balances = {
        "1.01.001": 50000.00,
        "3.01.001": 50000.00,
    }

    engine.set_opening_balances(
        balances=opening_balances,
        opening_date=datetime(2024, 1, 1),
        created_by="test@example.com",
    )

    # Revenue: +20k
    engine.generate_journal_entry_from_transaction(
        {"date": datetime(2024, 6, 1), "amount": 20000.00, "category": "sales",
         "transaction_type": "income", "description": "Sales"},
        created_by="system",
    )

    # Expense: -8k
    engine.generate_journal_entry_from_transaction(
        {"date": datetime(2024, 6, 15), "amount": 8000.00, "category": "cost_of_goods",
         "transaction_type": "expense", "description": "COGS"},
        created_by="system",
    )

    calculator = BalanceSheetCalculator(db_session, test_user.id)
    bs = calculator.calculate_balance_sheet(reference_date=date(2024, 6, 30))

    # Cash = 50000 + 20000 - 8000 = 62000
    assert bs.ativo_circulante == Decimal("62000.00")

    # PL = Capital 50000 + Net Income 12000 = 62000
    assert bs.patrimonio_liquido == Decimal("62000.00")

    # Should have "Lucros do Exercício" line in equity
    lucro_lines = [l for l in bs.equity_lines if "Lucros" in l.name]
    assert len(lucro_lines) == 1
    assert lucro_lines[0].balance == Decimal("12000.00")

    assert bs.is_balanced
