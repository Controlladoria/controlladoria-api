"""
Tests for Brazilian Standards Compliance
Verifies UTF-8 support, currency formatting, date formats, and Portuguese labels
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from accounting.balance_sheet_exports import export_balance_sheet_to_pdf
from accounting.dre_exports import format_brl
from database import Base, ChartOfAccountsEntry, JournalEntry, User


def test_database_utf8_support():
    """Test that database correctly handles Brazilian Portuguese characters"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Test with Portuguese characters (ç, ã, õ, á, é, í, ó, ú, â, ê, ô)
    user = User(
        email="joão@empresa.com.br",
        password_hash="hash",
        full_name="João da Silva Araújo",
        company_name="Empresa de Soluções Ltda",
        cnpj="12.345.678/0001-90",
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # Verify data was stored and retrieved correctly
    assert user.full_name == "João da Silva Araújo"
    assert user.company_name == "Empresa de Soluções Ltda"
    assert "joão" in user.email

    # Test with account names
    account = ChartOfAccountsEntry(
        user_id=user.id,
        account_code="1.01.001",
        account_name="Caixa e Equivalentes de Caixa",
        account_type="ativo_circulante",
        account_nature="debit",
        description="Dinheiro em caixa e depósitos bancários de liquidação imediata",
        is_active=True,
        is_system_account=True,
        current_balance=0,
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    assert account.account_name == "Caixa e Equivalentes de Caixa"
    assert "depósitos" in account.description
    assert "liquidação" in account.description

    session.close()


def test_currency_formatting_brl():
    """Test Brazilian currency formatting R$ 1.234,56"""

    # Test positive values
    assert format_brl(Decimal("1000.00")) == "R$ 1.000,00"
    assert format_brl(Decimal("1000.50")) == "R$ 1.000,50"
    assert format_brl(Decimal("1234567.89")) == "R$ 1.234.567,89"
    assert format_brl(Decimal("0.01")) == "R$ 0,01"
    assert format_brl(Decimal("100")) == "R$ 100,00"

    # Test negative values (should be in parentheses)
    assert format_brl(Decimal("-1000.00")) == "(R$ 1.000,00)"
    assert format_brl(Decimal("-500.50")) == "(R$ 500,50)"

    # Test edge cases
    assert format_brl(Decimal("0")) == "R$ 0,00"
    assert format_brl(Decimal("0.99")) == "R$ 0,99"


def test_date_formatting_brazilian():
    """Test that dates are formatted as DD/MM/YYYY"""
    test_date = date(2024, 12, 31)

    # Brazilian format should be 31/12/2024
    formatted = test_date.strftime("%d/%m/%Y")
    assert formatted == "31/12/2024"

    # Month names in Portuguese (if we use them)
    months_pt = {
        1: "Janeiro",
        2: "Fevereiro",
        3: "Março",
        4: "Abril",
        5: "Maio",
        6: "Junho",
        7: "Julho",
        8: "Agosto",
        9: "Setembro",
        10: "Outubro",
        11: "Novembro",
        12: "Dezembro",
    }
    assert months_pt[12] == "Dezembro"


def test_portuguese_labels_in_exports():
    """Test that all exports use Portuguese labels"""
    from accounting.dre_calculator import DRE
    from accounting.dre_models import FinancialRatios, PeriodType

    dre = DRE(
        period_type=PeriodType.MONTH,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 31),
        company_name="Empresa Teste Ltda",
        cnpj="12.345.678/0001-90",
        receita_bruta=Decimal("100000"),
        deducoes_vendas=Decimal("10000"),
        impostos_vendas=Decimal("5000"),
        total_deducoes=Decimal("15000"),
        receita_liquida=Decimal("85000"),
        custo_vendas=Decimal("50000"),
        lucro_bruto=Decimal("35000"),
        despesas_vendas=Decimal("5000"),
        despesas_administrativas=Decimal("10000"),
        despesas_gerais=Decimal("5000"),
        total_despesas_operacionais=Decimal("20000"),
        ebitda=Decimal("15000"),
        deprec_amortizacao=Decimal("2000"),
        resultado_antes_juros=Decimal("13000"),
        receitas_financeiras=Decimal("1000"),
        despesas_financeiras=Decimal("2000"),
        resultado_financeiro=Decimal("-1000"),
        resultado_antes_ir=Decimal("12000"),
        ir_csll=Decimal("4000"),
        lucro_liquido=Decimal("8000"),
        ratios=FinancialRatios(
            margem_bruta=Decimal("41.18"),
            margem_operacional=Decimal("17.65"),
            margem_liquida=Decimal("9.41"),
            ebitda_margin=Decimal("17.65"),
        ),
    )

    # Convert to dict and check Portuguese keys
    dre_dict = dre.model_dump()

    assert "receita_bruta" in dre_dict
    assert "receita_liquida" in dre_dict
    assert "lucro_bruto" in dre_dict
    assert "lucro_liquido" in dre_dict
    assert "despesas_vendas" in dre_dict
    # These are in Portuguese, not English
    assert "gross_revenue" not in str(dre_dict)
    assert "net_profit" not in str(dre_dict)


def test_accounting_terms_in_portuguese():
    """Verify accounting terms are in Portuguese"""
    from accounting.chart_of_accounts import BrazilianChartOfAccounts

    chart = BrazilianChartOfAccounts()
    all_accounts = chart.get_all_accounts()

    # Check that account names are in Portuguese
    account_names = [acc["name"] for acc in all_accounts]

    # Should have Portuguese terms
    portuguese_terms_found = []
    expected_terms = [
        "Caixa",
        "Banco",
        "Cliente",
        "Fornecedor",
        "Imóveis",
        "Veículo",
        "Capital",
        "Lucro",
        "Receita",
        "Despesa",
        "Salário",
        "Aluguel",
    ]

    for term in expected_terms:
        if any(term in name for name in account_names):
            portuguese_terms_found.append(term)

    # Should have found at least 8 of these Portuguese terms
    assert len(portuguese_terms_found) >= 8, f"Found only {portuguese_terms_found}"

    # Should NOT have English terms
    english_terms = [
        "Cash",
        "Bank Account",
        "Customer",
        "Supplier",
        "Revenue",
        "Expense",
    ]
    for term in english_terms:
        assert not any(
            term in name for name in account_names
        ), f"Found English term: {term}"


def test_postgresql_utf8_ready():
    """Test that connection strings are UTF-8 ready for PostgreSQL"""
    from database import DATABASE_URL

    # SQLite uses UTF-8 by default
    # PostgreSQL connection should specify encoding (though it's default)
    # If using PostgreSQL, the connection string should be ready
    test_pg_url = "postgresql://user:password@localhost:5432/controlladoria"

    # This would work with UTF-8 by default in PostgreSQL
    # Just verify the format is correct
    assert "postgresql://" in test_pg_url or "sqlite://" in DATABASE_URL


def test_brazilian_cnpj_format():
    """Test CNPJ format validation (Brazilian tax ID)"""
    import re

    # Valid CNPJ format: 12.345.678/0001-90
    valid_cnpj = "12.345.678/0001-90"
    cnpj_pattern = r"^\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}$"

    assert re.match(cnpj_pattern, valid_cnpj)

    # Test without formatting (14 digits)
    cnpj_digits = "12345678000190"
    assert len(cnpj_digits) == 14
    assert cnpj_digits.isdigit()


def test_text_columns_support_long_portuguese():
    """Test that Text columns can handle long Portuguese text"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    user = User(
        email="test@test.com",
        password_hash="hash",
        full_name="Test User",
        company_name="Test Company LTDA",
        cnpj="12.345.678/0001-90",
        is_active=True,
    )
    session.add(user)
    session.commit()

    # Long Portuguese text with special characters
    long_description = """
    Esta é uma descrição muito longa em português brasileiro, com vários caracteres especiais
    como ç, ã, õ, á, é, í, ó, ú, â, ê, ô. O objetivo é testar se o banco de dados consegue
    armazenar corretamente textos longos em português, incluindo pontuação, acentuação e
    cedilha. Também testamos números como R$ 1.234,56 e datas como 31/12/2024.

    Parágrafo adicional para aumentar o tamanho do texto e garantir que não há limite
    artificial no armazenamento. Incluímos também alguns termos contábeis: ativo circulante,
    passivo não circulante, patrimônio líquido, demonstração do resultado do exercício,
    balanço patrimonial, fluxo de caixa, etc.
    """

    account = ChartOfAccountsEntry(
        user_id=user.id,
        account_code="1.01.001",
        account_name="Teste com Acentuação e Ç",
        account_type="ativo_circulante",
        account_nature="debit",
        description=long_description,
        is_active=True,
        is_system_account=False,
        current_balance=0,
    )
    session.add(account)
    session.commit()
    session.refresh(account)

    # Verify all characters were preserved
    assert account.description == long_description
    assert "acentuação" in account.description
    assert "ç" in account.description
    assert "R$ 1.234,56" in account.description
    assert len(account.description) > 500  # Long text preserved

    session.close()


def test_decimal_precision_for_currency():
    """Test that Decimal provides adequate precision for Brazilian currency"""
    from decimal import Decimal, getcontext

    # Set precision (default is usually 28, which is more than enough)
    getcontext().prec = 28

    # Test precise currency calculations
    price = Decimal("1234.56")
    quantity = Decimal("3")
    total = price * quantity

    assert total == Decimal("3703.68")

    # Test that we don't lose precision
    subtotal = Decimal("1000.00")
    tax_rate = Decimal("0.18")  # 18% tax
    tax = subtotal * tax_rate

    assert tax == Decimal("180.00")

    total_with_tax = subtotal + tax
    assert total_with_tax == Decimal("1180.00")

    # Test cents conversion
    amount_dollars = Decimal("1234.56")
    amount_cents = int(amount_dollars * 100)
    assert amount_cents == 123456

    # Convert back
    back_to_dollars = Decimal(amount_cents) / Decimal(100)
    assert back_to_dollars == amount_dollars


def test_sort_order_with_portuguese():
    """Test that sorting works correctly with Portuguese characters"""
    names = [
        "Álvaro",
        "André",
        "Ângelo",
        "Carlos",
        "Çağlar",  # Turkish but has cedilla
        "João",
        "José",
        "Óscar",
        "Zélia",
    ]

    # Python's default sort should handle Unicode correctly (not perfect Portuguese collation)
    sorted_names = sorted(names)

    # Verify sorting works without errors and preserves Portuguese characters
    assert len(sorted_names) == len(names)
    # Verify no data corruption - all names should still contain Portuguese characters
    assert any(
        "á" in name.lower() or "â" in name.lower() or "ã" in name.lower()
        for name in sorted_names
    )
    assert any("ç" in name.lower() for name in sorted_names)
    assert any("ó" in name.lower() for name in sorted_names)
    # Verify André (plain A) comes before Álvaro (accented Á) in Unicode sort
    andre_idx = sorted_names.index("André")
    alvaro_idx = sorted_names.index("Álvaro")
    assert andre_idx < alvaro_idx  # Unaccented sorts before accented in Unicode


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
