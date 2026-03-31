"""
Tests for Daily Cash Flow (Fluxo de Caixa Diário) - V2
Tests the DRE-like daily breakdown and bank-by-bank tracking
"""

from datetime import date
from decimal import Decimal

import pytest

from accounting.cash_flow_daily import (
    DailyCashFlow,
    DailyCashFlowCalculator,
    DailyBankEntry,
    DailyDREEntry,
    _classify_transaction,
)


@pytest.fixture
def calculator():
    return DailyCashFlowCalculator()


@pytest.fixture
def sample_transactions():
    """Sample transactions for a 3-day period"""
    return [
        # Day 1: Revenue + Variable Cost
        {
            "date": "2024-06-01",
            "amount": 10000.00,
            "category": "receita_vendas_produtos",
            "transaction_type": "income",
            "description": "Product sales",
            "bank_account": "Itaú",
        },
        {
            "date": "2024-06-01",
            "amount": 3000.00,
            "category": "cmv",
            "transaction_type": "expense",
            "description": "Cost of goods",
            "bank_account": "Itaú",
        },
        # Day 2: Revenue + Admin expense
        {
            "date": "2024-06-02",
            "amount": 5000.00,
            "category": "receita_servicos",
            "transaction_type": "income",
            "description": "Service revenue",
            "bank_account": "Bradesco",
        },
        {
            "date": "2024-06-02",
            "amount": 1500.00,
            "category": "aluguel",
            "transaction_type": "expense",
            "description": "Rent",
            "bank_account": "Itaú",
        },
        # Day 3: Deductions + Commercial expense
        {
            "date": "2024-06-03",
            "amount": 8000.00,
            "category": "receita_vendas_produtos",
            "transaction_type": "income",
            "description": "More sales",
            "bank_account": "Itaú",
        },
        {
            "date": "2024-06-03",
            "amount": 500.00,
            "category": "descontos_concedidos",
            "transaction_type": "expense",
            "description": "Discounts",
        },
        {
            "date": "2024-06-03",
            "amount": 800.00,
            "category": "marketing_publicidade",
            "transaction_type": "expense",
            "description": "Marketing",
            "bank_account": "Bradesco",
        },
    ]


# ===== CLASSIFICATION TESTS =====


def test_classify_revenue():
    assert _classify_transaction("receita_vendas_produtos") == "receita_bruta"
    assert _classify_transaction("receita_servicos") == "receita_bruta"
    assert _classify_transaction("receita_locacao") == "receita_bruta"
    assert _classify_transaction("receita_comissoes") == "receita_bruta"


def test_classify_deductions():
    assert _classify_transaction("devolucoes") == "deducao"
    assert _classify_transaction("descontos_concedidos") == "deducao"
    assert _classify_transaction("impostos_sobre_vendas") == "deducao"


def test_classify_variable_costs():
    assert _classify_transaction("cmv") == "custo_variavel"
    assert _classify_transaction("materia_prima") == "custo_variavel"
    assert _classify_transaction("comissoes_sobre_vendas") == "custo_variavel"


def test_classify_fixed_admin():
    assert _classify_transaction("aluguel") == "custo_fixo_admin"
    assert _classify_transaction("salarios_administrativos") == "custo_fixo_admin"
    assert _classify_transaction("agua_energia") == "custo_fixo_admin"


def test_classify_fixed_commercial():
    assert _classify_transaction("marketing_publicidade") == "custo_fixo_comercial"
    assert _classify_transaction("fretes") == "custo_fixo_comercial"


def test_classify_non_operating():
    assert _classify_transaction("receita_financeira") == "receita_nao_operacional"
    assert _classify_transaction("irpj") == "despesa_nao_operacional"
    assert _classify_transaction("csll") == "despesa_nao_operacional"


def test_classify_alias_resolution():
    """V1 category names should resolve through aliases"""
    # "sales" -> "receita_vendas_produtos" via alias
    result = _classify_transaction("sales")
    assert result == "receita_bruta"


# ===== DAILY DRE ENTRY TESTS =====


def test_daily_dre_entry_calculate():
    entry = DailyDREEntry(day=date(2024, 6, 1))
    entry.receita_bruta = Decimal("10000")
    entry.total_deducoes = Decimal("1000")
    entry.total_custos_variaveis = Decimal("3000")
    entry.custos_fixos_administrativos = Decimal("500")
    entry.custos_fixos_comerciais = Decimal("200")
    entry.receitas_nao_operacionais = Decimal("100")
    entry.despesas_nao_operacionais = Decimal("50")

    entry.calculate()

    assert entry.receita_liquida == Decimal("9000")     # 10000 - 1000
    assert entry.margem_contribuicao == Decimal("6000")  # 9000 - 3000
    assert entry.total_custos_fixos == Decimal("700")    # 500 + 200
    assert entry.resultado_operacional == Decimal("5300")  # 6000 - 700
    assert entry.resultado_nao_operacional == Decimal("50")  # 100 - 50
    assert entry.resultado_liquido == Decimal("5350")    # 5300 + 50


# ===== BANK ENTRY TESTS =====


def test_daily_bank_entry_calculate():
    entry = DailyBankEntry(
        bank_name="Itaú",
        day=date(2024, 6, 1),
        opening_balance=Decimal("5000"),
        total_inflows=Decimal("10000"),
        total_outflows=Decimal("3000"),
    )
    entry.calculate_closing()

    assert entry.closing_balance == Decimal("12000")  # 5000 + 10000 - 3000


# ===== CALCULATOR TESTS =====


def test_calculate_basic_daily_cash_flow(calculator, sample_transactions):
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
        company_name="Test Company",
    )

    assert isinstance(result, DailyCashFlow)
    assert result.company_name == "Test Company"
    assert len(result.daily_dre_entries) == 3  # 3 days


def test_daily_dre_day1_values(calculator, sample_transactions):
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
    )

    day1 = result.daily_dre_entries[0]
    assert day1.day == date(2024, 6, 1)
    assert day1.receita_bruta == Decimal("10000")
    assert day1.total_custos_variaveis == Decimal("3000")
    assert day1.margem_contribuicao == Decimal("7000")  # 10000 - 3000
    assert day1.resultado_liquido == Decimal("7000")


def test_daily_dre_day2_values(calculator, sample_transactions):
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
    )

    day2 = result.daily_dre_entries[1]
    assert day2.day == date(2024, 6, 2)
    assert day2.receita_bruta == Decimal("5000")
    assert day2.custos_fixos_administrativos == Decimal("1500")
    assert day2.margem_contribuicao == Decimal("5000")  # 5000 - 0 variable
    assert day2.resultado_operacional == Decimal("3500")  # 5000 - 1500


def test_daily_dre_day3_values(calculator, sample_transactions):
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
    )

    day3 = result.daily_dre_entries[2]
    assert day3.day == date(2024, 6, 3)
    assert day3.receita_bruta == Decimal("8000")
    assert day3.total_deducoes == Decimal("500")
    assert day3.receita_liquida == Decimal("7500")
    assert day3.custos_fixos_comerciais == Decimal("800")


def test_accumulated_result(calculator, sample_transactions):
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
    )

    # Accumulated should be running sum of daily resultado_liquido
    day1 = result.daily_dre_entries[0]
    day2 = result.daily_dre_entries[1]
    day3 = result.daily_dre_entries[2]

    assert day1.resultado_acumulado == day1.resultado_liquido
    assert day2.resultado_acumulado == day1.resultado_liquido + day2.resultado_liquido
    assert day3.resultado_acumulado == (
        day1.resultado_liquido + day2.resultado_liquido + day3.resultado_liquido
    )


def test_bank_tracking(calculator, sample_transactions):
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
        initial_bank_balances={"Itaú": Decimal("5000"), "Bradesco": Decimal("2000")},
    )

    # Should have 2 banks
    assert "Itaú" in result.bank_entries
    assert "Bradesco" in result.bank_entries


def test_bank_itau_day1(calculator, sample_transactions):
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
        initial_bank_balances={"Itaú": Decimal("5000")},
    )

    itau_entries = result.bank_entries["Itaú"]
    day1_itau = [e for e in itau_entries if e.day == date(2024, 6, 1)][0]

    assert day1_itau.opening_balance == Decimal("5000")
    assert day1_itau.total_inflows == Decimal("10000")
    assert day1_itau.total_outflows == Decimal("3000")
    assert day1_itau.closing_balance == Decimal("12000")  # 5000 + 10000 - 3000


def test_bank_rolling_balance(calculator, sample_transactions):
    """Day 2 opening should equal Day 1 closing"""
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
        initial_bank_balances={"Itaú": Decimal("5000")},
    )

    itau_entries = result.bank_entries["Itaú"]
    day1 = [e for e in itau_entries if e.day == date(2024, 6, 1)][0]
    day2 = [e for e in itau_entries if e.day == date(2024, 6, 2)][0]

    assert day2.opening_balance == day1.closing_balance


def test_monthly_totals(calculator, sample_transactions):
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
    )

    assert "2024-06" in result.monthly_totals
    monthly = result.monthly_totals["2024-06"]

    # Monthly total should be sum of all 3 days
    total_revenue = sum(
        e.receita_bruta for e in result.daily_dre_entries
    )
    assert monthly.receita_bruta == total_revenue


def test_empty_days_included(calculator):
    """Days with no transactions should still appear"""
    txns = [
        {
            "date": "2024-06-01",
            "amount": 1000.00,
            "category": "receita_vendas_produtos",
            "transaction_type": "income",
        },
        {
            "date": "2024-06-03",
            "amount": 500.00,
            "category": "receita_vendas_produtos",
            "transaction_type": "income",
        },
    ]

    result = calculator.calculate(
        transactions=txns,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
    )

    assert len(result.daily_dre_entries) == 3
    # Day 2 should be empty
    day2 = result.daily_dre_entries[1]
    assert day2.receita_bruta == Decimal("0")
    assert day2.resultado_liquido == Decimal("0")


def test_to_dict_serialization(calculator, sample_transactions):
    result = calculator.calculate(
        transactions=sample_transactions,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
    )

    d = result.to_dict()

    assert d["company_name"] == "Test Company"
    assert d["cnpj"] == "12.345.678/0001-90"
    assert d["start_date"] == "2024-06-01"
    assert d["end_date"] == "2024-06-03"
    assert len(d["daily_dre"]) == 3
    assert "2024-06" in d["monthly_totals"]

    # Verify all values are float (JSON-serializable)
    for day_data in d["daily_dre"]:
        assert isinstance(day_data["receita_bruta"], float)
        assert isinstance(day_data["resultado_acumulado"], float)


def test_default_bank_name(calculator):
    """Transactions without bank_account should go to 'Principal'"""
    txns = [
        {
            "date": "2024-06-01",
            "amount": 1000.00,
            "category": "receita_vendas_produtos",
            "transaction_type": "income",
            # No bank_account specified
        },
    ]

    result = calculator.calculate(
        transactions=txns,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 1),
    )

    assert "Principal" in result.bank_entries


def test_date_filtering(calculator):
    """Transactions outside the date range should be excluded"""
    txns = [
        {"date": "2024-05-31", "amount": 999, "category": "receita_vendas_produtos", "transaction_type": "income"},
        {"date": "2024-06-01", "amount": 1000, "category": "receita_vendas_produtos", "transaction_type": "income"},
        {"date": "2024-06-04", "amount": 999, "category": "receita_vendas_produtos", "transaction_type": "income"},
    ]

    result = calculator.calculate(
        transactions=txns,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 3),
    )

    # Only the June 1st transaction should be included
    total_revenue = sum(e.receita_bruta for e in result.daily_dre_entries)
    assert total_revenue == Decimal("1000")
