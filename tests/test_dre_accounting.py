"""
Comprehensive tests for DRE (Income Statement) accounting module
Tests Brazilian accounting standards compliance
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from accounting import (
    DRECalculator,
    PeriodType,
    calculate_dre,
    export_dre_to_csv,
    export_dre_to_excel,
    export_dre_to_pdf,
    get_period_dates,
)

# =========================================
# TEST FIXTURES
# =========================================


@pytest.fixture
def sample_transactions():
    """Sample transaction data for testing"""
    today = date.today()

    return [
        # Revenue transactions
        {
            "date": today - timedelta(days=5),
            "amount": Decimal("10000.00"),
            "category": "sales",
            "transaction_type": "income",
            "description": "Product sales",
        },
        {
            "date": today - timedelta(days=3),
            "amount": Decimal("5000.00"),
            "category": "services",
            "transaction_type": "income",
            "description": "Service revenue",
        },
        # Deduction - Sales taxes
        {
            "date": today - timedelta(days=5),
            "amount": Decimal("1800.00"),
            "category": "sales_tax_icms",
            "transaction_type": "expense",
            "description": "ICMS on sales",
        },
        {
            "date": today - timedelta(days=5),
            "amount": Decimal("195.00"),
            "category": "sales_tax_pis",
            "transaction_type": "expense",
            "description": "PIS",
        },
        {
            "date": today - timedelta(days=5),
            "amount": Decimal("900.00"),
            "category": "sales_tax_cofins",
            "transaction_type": "expense",
            "description": "COFINS",
        },
        # Cost of goods sold
        {
            "date": today - timedelta(days=4),
            "amount": Decimal("3000.00"),
            "category": "cogs",
            "transaction_type": "expense",
            "description": "Cost of goods sold",
        },
        # Operating expenses
        {
            "date": today - timedelta(days=2),
            "amount": Decimal("1500.00"),
            "category": "salaries",
            "transaction_type": "expense",
            "description": "Salaries",
        },
        {
            "date": today - timedelta(days=2),
            "amount": Decimal("500.00"),
            "category": "rent",
            "transaction_type": "expense",
            "description": "Office rent",
        },
        {
            "date": today - timedelta(days=1),
            "amount": Decimal("200.00"),
            "category": "utilities",
            "transaction_type": "expense",
            "description": "Utilities",
        },
        {
            "date": today - timedelta(days=1),
            "amount": Decimal("300.00"),
            "category": "marketing",
            "transaction_type": "expense",
            "description": "Marketing expenses",
        },
        # Financial result
        {
            "date": today - timedelta(days=1),
            "amount": Decimal("100.00"),
            "category": "interest_income",
            "transaction_type": "income",
            "description": "Interest income",
        },
        {
            "date": today - timedelta(days=1),
            "amount": Decimal("50.00"),
            "category": "bank_fees",
            "transaction_type": "expense",
            "description": "Bank fees",
        },
    ]


# =========================================
# CALCULATOR TESTS
# =========================================


def test_dre_calculator_basic(sample_transactions):
    """Test basic DRE calculation"""
    calculator = DRECalculator()

    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculator.calculate_dre_from_transactions(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
    )

    # Verify basic structure
    assert dre.period_type == PeriodType.CUSTOM
    assert dre.start_date == period_start
    assert dre.end_date == period_end
    assert dre.company_name == "Test Company"
    assert dre.cnpj == "12.345.678/0001-90"
    assert dre.transaction_count == len(sample_transactions)


def test_dre_revenue_calculation(sample_transactions):
    """Test revenue section calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Revenue = 10,000 (sales) + 5,000 (services) = 15,000
    assert dre.receita_bruta == Decimal("15000.00")


def test_dre_deductions_calculation(sample_transactions):
    """Test deduction section calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Deductions = 1,800 (ICMS) + 195 (PIS) + 900 (COFINS) = 2,895
    assert dre.total_deducoes == Decimal("2895.00")


def test_dre_net_revenue_calculation(sample_transactions):
    """Test net revenue calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Net Revenue = 15,000 - 2,895 = 12,105
    assert dre.receita_liquida == Decimal("12105.00")


def test_dre_cost_calculation(sample_transactions):
    """Test cost section calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Costs = 3,000 (COGS)
    assert dre.total_custos == Decimal("3000.00")


def test_dre_gross_profit_calculation(sample_transactions):
    """Test gross profit calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Gross Profit = 12,105 (net revenue) - 3,000 (costs) = 9,105
    assert dre.lucro_bruto == Decimal("9105.00")


def test_dre_operating_expenses_calculation(sample_transactions):
    """Test operating expenses calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Administrative: 1,500 (salaries) + 500 (rent) + 200 (utilities) = 2,200
    # Sales: 300 (marketing)
    # Total Operating Expenses = 2,200 + 300 = 2,500
    assert dre.total_despesas_operacionais == Decimal("2500.00")


def test_dre_ebitda_calculation(sample_transactions):
    """Test EBITDA calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # EBITDA = 9,105 (gross profit) - 2,500 (operating expenses) = 6,605
    assert dre.ebitda == Decimal("6605.00")


def test_dre_financial_result_calculation(sample_transactions):
    """Test financial result calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Financial Revenue = 100 (interest income)
    # Financial Expenses = 50 (bank fees)
    # Net Financial Result = 100 - 50 = 50
    assert dre.receitas_financeiras == Decimal("100.00")
    assert dre.despesas_financeiras == Decimal("50.00")
    assert dre.resultado_financeiro == Decimal("50.00")


def test_dre_net_profit_calculation(sample_transactions):
    """Test net profit calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # EBIT = EBITDA (no depreciation in sample) = 6,605
    # LAIR = EBIT + Financial Result = 6,605 + 50 = 6,655
    # Net Profit = LAIR (no taxes in sample) = 6,655
    assert dre.lucro_liquido == Decimal("6655.00")


def test_dre_financial_ratios(sample_transactions):
    """Test financial ratios calculation - V2: all ratios vs Receita Bruta"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Receita Bruta = 15,000
    # Margem Contribuição = 9,105  (same as lucro_bruto)
    # EBITDA = 6,605
    # Net Profit = 6,655

    # V2: All ratios calculated vs Receita Bruta (15,000)
    # Margem Contribuição % = (9,105 / 15,000) * 100 = 60.70%
    # EBITDA Margin = (6,605 / 15,000) * 100 = 44.03%
    # Net Margin = (6,655 / 15,000) * 100 = 44.37%
    # margem_bruta = margem_contribuicao (backward compat)

    assert abs(dre.ratios.margem_contribuicao - 60.70) < 0.1
    assert abs(dre.ratios.margem_bruta - 60.70) < 0.1  # Legacy = margem_contribuicao
    assert abs(dre.ratios.margem_ebitda - 44.03) < 0.1
    assert abs(dre.ratios.margem_liquida - 44.37) < 0.1


# =========================================
# PERIOD CALCULATION TESTS
# =========================================


def test_get_period_dates_day():
    """Test day period calculation"""
    ref_date = date(2024, 3, 15)
    start, end = get_period_dates(PeriodType.DAY, ref_date)

    assert start == ref_date
    assert end == ref_date


def test_get_period_dates_week():
    """Test week period calculation (Monday to Sunday)"""
    # Thursday, March 14, 2024
    ref_date = date(2024, 3, 14)
    start, end = get_period_dates(PeriodType.WEEK, ref_date)

    # Should return Monday (Mar 11) to Sunday (Mar 17)
    assert start == date(2024, 3, 11)  # Monday
    assert end == date(2024, 3, 17)  # Sunday


def test_get_period_dates_month():
    """Test month period calculation"""
    ref_date = date(2024, 3, 15)
    start, end = get_period_dates(PeriodType.MONTH, ref_date)

    assert start == date(2024, 3, 1)  # First day of March
    assert end == date(2024, 3, 31)  # Last day of March


def test_get_period_dates_year():
    """Test year period calculation"""
    ref_date = date(2024, 6, 15)
    start, end = get_period_dates(PeriodType.YEAR, ref_date)

    assert start == date(2024, 1, 1)  # January 1
    assert end == date(2024, 12, 31)  # December 31


# =========================================
# FILTERING TESTS
# =========================================


def test_dre_date_filtering():
    """Test that only transactions within period are included"""
    transactions = [
        {
            "date": date(2024, 1, 15),
            "amount": Decimal("1000.00"),
            "category": "sales",
            "transaction_type": "income",
        },
        {
            "date": date(2024, 2, 15),
            "amount": Decimal("2000.00"),
            "category": "sales",
            "transaction_type": "income",
        },
        {
            "date": date(2024, 3, 15),
            "amount": Decimal("3000.00"),
            "category": "sales",
            "transaction_type": "income",
        },
    ]

    # Calculate DRE for February only
    dre = calculate_dre(
        transactions=transactions,
        period_type=PeriodType.MONTH,
        start_date=date(2024, 2, 1),
        end_date=date(2024, 2, 29),
    )

    # Should only include February transaction
    assert dre.receita_bruta == Decimal("2000.00")
    assert dre.transaction_count == 1


def test_dre_empty_transactions():
    """Test DRE with no transactions"""
    dre = calculate_dre(
        transactions=[],
        period_type=PeriodType.MONTH,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )

    assert dre.receita_bruta == Decimal("0")
    assert dre.lucro_liquido == Decimal("0")
    assert dre.transaction_count == 0


# =========================================
# EXPORT TESTS
# =========================================


def test_export_dre_to_pdf(sample_transactions):
    """Test PDF export"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
        company_name="Test Company",
        cnpj="12.345.678/0001-90",
    )

    # Export to PDF
    pdf_bytes = export_dre_to_pdf(dre)

    # Verify PDF was generated
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    # PDF files start with %PDF
    assert pdf_bytes[:4] == b"%PDF"


def test_export_dre_to_excel(sample_transactions):
    """Test Excel export"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
        company_name="Test Company",
    )

    # Export to Excel
    excel_bytes = export_dre_to_excel(dre)

    # Verify Excel was generated
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 0
    # Excel files start with PK (ZIP archive signature)
    assert excel_bytes[:2] == b"PK"


def test_export_dre_to_csv(sample_transactions):
    """Test CSV export"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
        company_name="Test Company",
    )

    # Export to CSV
    csv_string = export_dre_to_csv(dre)

    # Verify CSV was generated
    assert isinstance(csv_string, str)
    assert len(csv_string) > 0
    assert "DRE GERENCIAL" in csv_string
    assert "Receita Bruta" in csv_string
    assert "Lucro Líquido" in csv_string


# =========================================
# EDGE CASE TESTS
# =========================================


def test_dre_with_string_dates():
    """Test DRE calculation with string dates"""
    transactions = [
        {
            "date": "2024-01-15",  # String format
            "amount": Decimal("1000.00"),
            "category": "sales",
            "transaction_type": "income",
        }
    ]

    dre = calculate_dre(
        transactions=transactions,
        period_type=PeriodType.MONTH,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
    )

    assert dre.receita_bruta == Decimal("1000.00")


def test_dre_with_missing_category():
    """Test DRE with uncategorized transactions"""
    transactions = [
        {
            "date": date.today(),
            "amount": Decimal("500.00"),
            "category": None,  # Missing category
            "transaction_type": "expense",
        }
    ]

    dre = calculate_dre(
        transactions=transactions,
        period_type=PeriodType.DAY,
        start_date=date.today(),
        end_date=date.today(),
    )

    # Should track uncategorized
    assert dre.uncategorized_count == 1
    assert dre.uncategorized_amount == Decimal("500.00")


def test_dre_with_zero_net_revenue():
    """Test DRE with zero net revenue (avoid division by zero)"""
    transactions = []  # No transactions = zero revenue

    dre = calculate_dre(
        transactions=transactions,
        period_type=PeriodType.DAY,
        start_date=date.today(),
        end_date=date.today(),
    )

    # Ratios should be 0, not raise exception
    assert dre.ratios.margem_bruta == 0.0
    assert dre.ratios.margem_ebitda == 0.0
    assert dre.ratios.margem_liquida == 0.0


def test_dre_with_negative_profit():
    """Test DRE with negative profit (loss)"""
    transactions = [
        {
            "date": date.today(),
            "amount": Decimal("1000.00"),
            "category": "sales",
            "transaction_type": "income",
        },
        {
            "date": date.today(),
            "amount": Decimal("5000.00"),  # Expenses > Revenue
            "category": "cogs",
            "transaction_type": "expense",
        },
    ]

    dre = calculate_dre(
        transactions=transactions,
        period_type=PeriodType.DAY,
        start_date=date.today(),
        end_date=date.today(),
    )

    # Should have negative profit (loss)
    assert dre.lucro_bruto < Decimal("0")
    assert dre.lucro_liquido < Decimal("0")


# =========================================
# VALIDATION TESTS
# =========================================


def test_dre_detailed_lines_generation(sample_transactions):
    """Test that detailed line items are generated correctly"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Should have detailed lines
    assert len(dre.detailed_lines) > 0

    # Should have key line items (V2 structure)
    line_descriptions = [line.description for line in dre.detailed_lines]
    assert "RECEITA OPERACIONAL BRUTA" in line_descriptions
    assert "RECEITA OPERACIONAL LÍQUIDA" in line_descriptions
    assert "MARGEM DE CONTRIBUIÇÃO" in line_descriptions  # V2: replaces LUCRO BRUTO as primary
    assert "LUCRO BRUTO" in line_descriptions  # Legacy line still present
    assert "EBITDA" in line_descriptions
    assert "LUCRO LÍQUIDO DO EXERCÍCIO" in line_descriptions


def test_dre_formatted_output(sample_transactions):
    """Test formatted dict output"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
        company_name="Test Company",
    )

    formatted = dre.to_dict_formatted()

    # Verify formatting
    assert formatted["company_name"] == "Test Company"
    assert formatted["period_type"] == "custom"
    assert "receita_bruta" in formatted
    assert "R$" in formatted["receita_bruta"]  # Brazilian currency format
    assert "ratios" in formatted


# =========================================
# V2 DRE STRUCTURE TESTS
# =========================================


def test_dre_v2_variable_costs(sample_transactions):
    """Test V2 variable cost calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Variable costs = 3,000 (COGS, resolved from "cogs" alias -> "cmv")
    assert dre.total_custos_variaveis == Decimal("3000.00")
    assert dre.custos_variaveis_cmv == Decimal("3000.00")
    assert dre.custos_variaveis_csp == Decimal("0")
    assert dre.custos_variaveis_outros == Decimal("0")


def test_dre_v2_contribution_margin(sample_transactions):
    """Test V2 contribution margin calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Margem de Contribuição = Receita Líquida - Custos Variáveis
    # = 12,105 - 3,000 = 9,105
    assert dre.margem_contribuicao == Decimal("9105.00")
    # Legacy: lucro_bruto = margem_contribuicao
    assert dre.lucro_bruto == dre.margem_contribuicao


def test_dre_v2_fixed_costs(sample_transactions):
    """Test V2 fixed cost calculation"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Fixed admin: 1,500 (salaries->salarios_administrativos) + 500 (rent->aluguel)
    #   + 200 (utilities->agua_energia) = 2,200
    assert dre.despesas_administrativas == Decimal("2200.00")

    # Fixed commercial: 300 (marketing->marketing_publicidade)
    assert dre.despesas_vendas == Decimal("300.00")

    # Total fixed = 2,200 + 300 = 2,500
    assert dre.total_custos_fixos == Decimal("2500.00")
    # Legacy: total_despesas_operacionais = total_custos_fixos
    assert dre.total_despesas_operacionais == dre.total_custos_fixos


def test_dre_v2_ebitda_formula(sample_transactions):
    """Test V2 EBITDA formula: Margem Contribuição - Custos Fixos"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # V2: EBITDA = Margem de Contribuição - Total Custos Fixos
    # = 9,105 - 2,500 = 6,605
    assert dre.ebitda == dre.margem_contribuicao - dre.total_custos_fixos
    assert dre.ebitda == Decimal("6605.00")


def test_dre_v2_legacy_backward_compat(sample_transactions):
    """Test that all legacy fields are correctly populated"""
    period_start = date.today() - timedelta(days=7)
    period_end = date.today()

    dre = calculate_dre(
        transactions=sample_transactions,
        period_type=PeriodType.CUSTOM,
        start_date=period_start,
        end_date=period_end,
    )

    # Legacy field mappings
    assert dre.total_custos == dre.total_custos_variaveis
    assert dre.lucro_bruto == dre.margem_contribuicao
    assert dre.total_despesas_operacionais == dre.total_custos_fixos
    assert dre.custo_mercadorias_vendidas == dre.custos_variaveis_cmv
    assert dre.custo_servicos_prestados == dre.custos_variaveis_csp


def test_dre_v2_with_services():
    """Test V2 with service costs (CSP)"""
    today = date.today()
    transactions = [
        {
            "date": today,
            "amount": Decimal("20000.00"),
            "category": "receita_servicos",
            "transaction_type": "income",
        },
        {
            "date": today,
            "amount": Decimal("5000.00"),
            "category": "csp",
            "transaction_type": "expense",
        },
        {
            "date": today,
            "amount": Decimal("2000.00"),
            "category": "salarios_producao",
            "transaction_type": "expense",
        },
        {
            "date": today,
            "amount": Decimal("3000.00"),
            "category": "salarios_administrativos",
            "transaction_type": "expense",
        },
    ]

    dre = calculate_dre(
        transactions=transactions,
        period_type=PeriodType.DAY,
        start_date=today,
        end_date=today,
    )

    # Revenue = 20,000
    assert dre.receita_bruta == Decimal("20000.00")
    # Variable costs: CSP=5000 + Salários Produção=2000 = 7000
    assert dre.custos_variaveis_csp == Decimal("5000.00")
    assert dre.custos_variaveis_outros == Decimal("2000.00")
    assert dre.total_custos_variaveis == Decimal("7000.00")
    # Contribution margin = 20000 - 7000 = 13000
    assert dre.margem_contribuicao == Decimal("13000.00")
    # Fixed costs: Salários Admin = 3000
    assert dre.total_custos_fixos == Decimal("3000.00")
    # EBITDA = 13000 - 3000 = 10000
    assert dre.ebitda == Decimal("10000.00")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
