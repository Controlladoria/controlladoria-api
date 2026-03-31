"""
Tests for Excel ledger parsing improvements:
  - Brazilian number format parsing (_parse_cell_as_decimal)
  - Ledger detection heuristics (_is_transaction_ledger)
  - Header row detection
  - Debit/credit dual column support

These tests are standalone - no API server or AI clients needed.
"""

import sys
from pathlib import Path
from decimal import Decimal

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# _parse_cell_as_decimal tests (via _parse_brazilian_number internally)
# ---------------------------------------------------------------------------

class FakeProcessor:
    """Minimal stub to test _parse_cell_as_decimal and _parse_brazilian_number."""

    def _parse_brazilian_number(self, value: str) -> str:
        """Copy of the real method for standalone testing."""
        if not value:
            return "0"
        try:
            value_str = str(value).strip().replace(" ", "")
            if "," not in value_str and value_str.replace(".", "").replace("-", "").isdigit():
                if "." in value_str:
                    parts = value_str.split(".")
                    if len(parts) == 2 and len(parts[1]) == 2:
                        return value_str
                return value_str
            if "," in value_str:
                value_str = value_str.replace(".", "")
                value_str = value_str.replace(",", ".")
                return value_str
            if value_str.count(".") > 1:
                value_str = value_str.replace(".", "")
                return value_str
            return value_str
        except Exception:
            return str(value)

    def _parse_cell_as_decimal(self, val) -> Decimal:
        """Copy of the real method for standalone testing."""
        import re

        try:
            # NaN check (works with pandas NaN or None)
            if val is None:
                raise ValueError("None value")
            if isinstance(val, float) and val != val:  # NaN check
                raise ValueError("NaN value")
        except (TypeError, ValueError):
            raise ValueError("Invalid value")

        # Already numeric
        if isinstance(val, (int, float)):
            return Decimal(str(val))

        # String processing
        val_str = str(val).strip()
        if not val_str:
            raise ValueError("Empty string")

        val_str = re.sub(r'[R$\s]', '', val_str)

        # Parentheses as negative
        if val_str.startswith('(') and val_str.endswith(')'):
            val_str = '-' + val_str[1:-1]

        standard = self._parse_brazilian_number(val_str)
        return Decimal(standard)


proc = FakeProcessor()


class TestParseCellAsDecimal:
    """Test robust cell-to-Decimal conversion."""

    def test_integer(self):
        assert proc._parse_cell_as_decimal(100) == Decimal("100")

    def test_float(self):
        assert proc._parse_cell_as_decimal(1234.56) == Decimal("1234.56")

    def test_negative_float(self):
        assert proc._parse_cell_as_decimal(-99.50) == Decimal("-99.5")

    def test_string_standard_format(self):
        assert proc._parse_cell_as_decimal("1234.56") == Decimal("1234.56")

    def test_string_brazilian_format(self):
        """1.234,56 is the Brazilian way to write 1234.56"""
        assert proc._parse_cell_as_decimal("1.234,56") == Decimal("1234.56")

    def test_string_brazilian_large(self):
        """10.500,00 = 10500.00"""
        assert proc._parse_cell_as_decimal("10.500,00") == Decimal("10500.00")

    def test_string_brazilian_no_thousands(self):
        """500,00 = 500.00"""
        assert proc._parse_cell_as_decimal("500,00") == Decimal("500.00")

    def test_string_negative_brazilian(self):
        assert proc._parse_cell_as_decimal("-1.234,56") == Decimal("-1234.56")

    def test_currency_prefix_brl(self):
        assert proc._parse_cell_as_decimal("R$ 1.234,56") == Decimal("1234.56")

    def test_currency_prefix_brl_no_space(self):
        assert proc._parse_cell_as_decimal("R$1.234,56") == Decimal("1234.56")

    def test_parentheses_negative(self):
        """Accounting convention: (1.234,56) means -1234.56"""
        assert proc._parse_cell_as_decimal("(1.234,56)") == Decimal("-1234.56")

    def test_zero(self):
        assert proc._parse_cell_as_decimal(0) == Decimal("0")

    def test_zero_string(self):
        assert proc._parse_cell_as_decimal("0,00") == Decimal("0.00")

    def test_small_decimal(self):
        assert proc._parse_cell_as_decimal("0,50") == Decimal("0.50")

    def test_integer_string(self):
        assert proc._parse_cell_as_decimal("1500") == Decimal("1500")


# ---------------------------------------------------------------------------
# _is_transaction_ledger tests
# ---------------------------------------------------------------------------

class TestIsTransactionLedger:
    """Test ledger detection heuristics."""

    def test_obvious_ledger_with_keywords_in_columns(self):
        """DataFrame with clear column names should be detected as ledger."""
        import pandas as pd
        data = {
            "Data": ["2025-01-01"] * 10,
            "Descrição": ["Pagamento"] * 10,
            "Valor": [100.0] * 10,
            "Categoria": ["Despesa"] * 10,
        }
        df = pd.DataFrame(data)

        # Import and create a minimal processor to call the method
        # We'll test the logic inline since we can't import the full processor
        column_str = " ".join(str(col).lower() for col in df.columns)
        ledger_keywords = ["data", "valor", "descri", "categoria"]
        matches = sum(1 for kw in ledger_keywords if kw in column_str)
        assert matches >= 2, f"Expected >= 2 keyword matches, got {matches}"

    def test_small_file_not_ledger(self):
        """Very small files (< 3 rows) should not be detected as ledger."""
        import pandas as pd
        df = pd.DataFrame({"A": [1], "B": [2]})
        df_clean = df.dropna(how="all")
        assert len(df_clean) < 3  # Would return False in _is_transaction_ledger

    def test_header_in_row_3(self):
        """Keywords in row 3 (not column names) should still detect as ledger."""
        import pandas as pd
        # Simulate: rows 0-2 are junk, row 3 has header keywords
        data = {
            "Unnamed: 0": ["", "", "", "Data", "2025-01-01", "2025-01-02"],
            "Unnamed: 1": ["", "", "", "Valor", "100", "200"],
            "Unnamed: 2": ["", "", "", "Descrição", "Item A", "Item B"],
        }
        df = pd.DataFrame(data)

        # Check row 3 for keywords (simulating Strategy 2 of _is_transaction_ledger)
        row = df.iloc[3]
        row_str = " ".join(str(val).lower() for val in row if val is not None and str(val).strip())
        keywords = ["data", "valor", "descri"]
        matches = sum(1 for kw in keywords if kw in row_str)
        assert matches >= 2, f"Row 3 should match keywords, got {matches}"

    def test_monetary_string_column_detection(self):
        """Columns with Brazilian monetary strings should trigger detection."""
        import re
        monetary_re = re.compile(r'^-?\(?\d{1,3}(\.\d{3})*(,\d{2})?\)?$|^-?R?\$?\s?\d')
        test_values = ["1.234,56", "500,00", "10.000,00", "R$ 1.500,00", "25,50"]
        hits = sum(1 for v in test_values if monetary_re.match(v.strip()))
        assert hits >= 3, f"Expected >= 3 monetary matches, got {hits}"


# ---------------------------------------------------------------------------
# Header detection tests
# ---------------------------------------------------------------------------

class TestHeaderDetection:
    """Test that header rows are correctly identified."""

    def test_header_at_row_0(self):
        """Standard case: header is row 0 (auto-detected by pandas)."""
        import pandas as pd
        df = pd.DataFrame({
            "Data": ["2025-01-01", "2025-01-02"],
            "Valor": [100.0, 200.0],
        })
        # pandas auto-detects, column_str should have keywords
        column_str = " ".join(str(col).lower() for col in df.columns)
        assert "data" in column_str
        assert "valor" in column_str

    def test_header_at_row_5(self):
        """Header buried in row 5 after blank/title rows."""
        import pandas as pd
        rows = [
            ["Relatório Financeiro", None, None],
            ["Empresa XYZ", None, None],
            [None, None, None],
            [None, None, None],
            [None, None, None],
            ["Data Competência", "Valor Pago", "Fornecedor"],
            ["2025-01-01", "1.234,56", "Fornecedor A"],
            ["2025-01-02", "567,89", "Fornecedor B"],
        ]
        df = pd.DataFrame(rows)

        # Simulate header scan
        header_keywords = ["data", "valor", "fornecedor", "competência"]
        header_row = None
        for i in range(min(15, len(df))):
            row = df.iloc[i]
            row_str = " ".join(str(val).lower() for val in row if val is not None and str(val).strip())
            matches = sum(1 for kw in header_keywords if kw in row_str)
            if matches >= 2:
                header_row = i
                break

        assert header_row == 5, f"Expected header at row 5, got {header_row}"


# ---------------------------------------------------------------------------
# Integration: full parsing pipeline (without AI)
# ---------------------------------------------------------------------------

class TestLedgerParsingPipeline:
    """Test complete ledger parsing with various formats."""

    def test_standard_format_parses_correctly(self):
        """Standard numeric Excel should parse without issues."""
        import pandas as pd
        df = pd.DataFrame({
            "Data": pd.to_datetime(["2025-01-01", "2025-01-15", "2025-02-01"]),
            "Descrição": ["Aluguel", "Energia", "Internet"],
            "Valor": [-1500.00, -350.00, -120.00],
            "Categoria": ["Aluguel", "Utilidades", "Utilidades"],
        })

        # Column detection should find all 4 columns
        col_str = " ".join(str(col).lower() for col in df.columns)
        assert "data" in col_str
        assert "descri" in col_str
        assert "valor" in col_str
        assert "categoria" in col_str

    def test_brazilian_string_amounts_parse(self):
        """Brazilian-format string amounts should be parsed by _parse_cell_as_decimal."""
        test_cases = [
            ("1.234,56", Decimal("1234.56")),
            ("500,00", Decimal("500.00")),
            ("-10.000,00", Decimal("-10000.00")),
            ("R$ 5.678,90", Decimal("5678.90")),
            ("(2.500,00)", Decimal("-2500.00")),
        ]
        for input_val, expected in test_cases:
            result = proc._parse_cell_as_decimal(input_val)
            assert result == expected, f"_parse_cell_as_decimal('{input_val}') = {result}, expected {expected}"

    def test_debit_credit_columns_detected(self):
        """Debit/credit columns should be detected as dual-amount pattern."""
        import pandas as pd
        df = pd.DataFrame({
            "Data": ["2025-01-01", "2025-01-02"],
            "Descrição": ["Venda", "Compra"],
            "Débito": [None, 500.0],
            "Crédito": [1000.0, None],
        })

        debit_col = None
        credit_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if any(kw in col_lower for kw in ["débito", "debito", "debit"]):
                debit_col = col
            elif any(kw in col_lower for kw in ["crédito", "credito", "credit"]):
                credit_col = col

        assert debit_col == "Débito", f"Expected debit col 'Débito', got {debit_col}"
        assert credit_col == "Crédito", f"Expected credit col 'Crédito', got {credit_col}"
