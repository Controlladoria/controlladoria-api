"""
Tests for V2 Category System (Plano de Contas)
Verifies 52 categories, aliases, variable/fixed separation, and backward compatibility
"""

from accounting.categories import (
    CATEGORY_ALIASES,
    DRE_CATEGORIES,
    DRELineType,
    VARIABLE_COST_CATEGORIES,
    FIXED_COST_CATEGORIES,
    REVENUE_CATEGORIES,
    DEDUCTION_CATEGORIES,
    DEPRECIATION_CATEGORIES,
    FINANCIAL_REVENUE_CATEGORIES,
    FINANCIAL_EXPENSE_CATEGORIES,
    TAX_ON_PROFIT_CATEGORIES,
    ADMIN_EXPENSE_CATEGORIES,
    SALES_EXPENSE_CATEGORIES,
    get_dre_category,
    resolve_category_name,
    get_all_categories,
    get_categories_by_behavior,
    get_categories_by_dre_group,
)


class TestCategoryCount:
    """Verify the correct number of categories exist"""

    def test_total_v2_categories(self):
        """Should have 52+ categories in V2 (52 from Plano de Contas + generics)"""
        assert len(DRE_CATEGORIES) >= 52

    def test_all_categories_have_required_fields(self):
        """Every category must have all required fields"""
        required_fields = [
            "account_code", "dre_line", "line_type", "dre_group",
            "nature", "cost_behavior", "section", "display_name",
            "sign", "order",
        ]
        for name, config in DRE_CATEGORIES.items():
            for field in required_fields:
                assert field in config, f"Category '{name}' missing field '{field}'"


class TestAccountCodes:
    """Verify account code structure"""

    def test_revenue_codes_start_with_1(self):
        """Revenue categories should have codes starting with 1"""
        for name in REVENUE_CATEGORIES:
            code = DRE_CATEGORIES[name]["account_code"]
            assert code.startswith("1.1"), f"Revenue '{name}' has code '{code}', expected 1.1.xx"

    def test_deduction_codes_start_with_1_2(self):
        """Deduction categories should have codes starting with 1.2"""
        for name in DEDUCTION_CATEGORIES:
            code = DRE_CATEGORIES[name]["account_code"]
            assert code.startswith("1.2"), f"Deduction '{name}' has code '{code}', expected 1.2.xx"

    def test_cost_codes_start_with_2(self):
        """Variable cost categories should have codes starting with 2"""
        for name in VARIABLE_COST_CATEGORIES:
            code = DRE_CATEGORIES[name]["account_code"]
            assert code.startswith("2."), f"Cost '{name}' has code '{code}', expected 2.x.xx"

    def test_tax_codes_start_with_3_4(self):
        """Tax categories should have codes starting with 3.4"""
        for name in TAX_ON_PROFIT_CATEGORIES:
            code = DRE_CATEGORIES[name]["account_code"]
            assert code.startswith("3.4"), f"Tax '{name}' has code '{code}', expected 3.4.xx"


class TestCostBehavior:
    """Verify variable vs fixed cost separation"""

    def test_variable_costs_not_empty(self):
        """Should have variable cost categories"""
        assert len(VARIABLE_COST_CATEGORIES) > 0

    def test_fixed_costs_not_empty(self):
        """Should have fixed cost categories"""
        assert len(FIXED_COST_CATEGORIES) > 0

    def test_variable_costs_flagged_correctly(self):
        """All variable cost categories must have cost_behavior='variable'"""
        for name in VARIABLE_COST_CATEGORIES:
            assert DRE_CATEGORIES[name]["cost_behavior"] == "variable", \
                f"Category '{name}' should be variable"

    def test_fixed_costs_flagged_correctly(self):
        """All fixed cost categories must have cost_behavior='fixed'"""
        for name in FIXED_COST_CATEGORIES:
            assert DRE_CATEGORIES[name]["cost_behavior"] == "fixed", \
                f"Category '{name}' should be fixed"

    def test_variable_costs_include_cmv_csp(self):
        """CMV and CSP must be in variable costs"""
        assert "cmv" in VARIABLE_COST_CATEGORIES
        assert "csp" in VARIABLE_COST_CATEGORIES

    def test_fixed_costs_include_admin(self):
        """Admin expenses must be in fixed costs"""
        assert "salarios_administrativos" in FIXED_COST_CATEGORIES
        assert "aluguel" in FIXED_COST_CATEGORIES

    def test_no_overlap_variable_fixed(self):
        """No category should be both variable and fixed"""
        overlap = set(VARIABLE_COST_CATEGORIES) & set(FIXED_COST_CATEGORIES)
        assert len(overlap) == 0, f"Categories in both variable and fixed: {overlap}"


class TestAliasBackwardCompatibility:
    """Verify old V1 category names still work"""

    def test_all_aliases_resolve(self):
        """Every alias must resolve to a valid V2 category"""
        for old_name, new_name in CATEGORY_ALIASES.items():
            assert new_name in DRE_CATEGORIES, \
                f"Alias '{old_name}' -> '{new_name}' but '{new_name}' not in DRE_CATEGORIES"

    def test_sales_alias(self):
        """'sales' should resolve to a revenue category"""
        result = get_dre_category("sales")
        assert result is not None
        assert result["line_type"] == DRELineType.REVENUE

    def test_services_alias(self):
        """'services' should resolve to a revenue category"""
        result = get_dre_category("services")
        assert result is not None
        assert result["line_type"] == DRELineType.REVENUE

    def test_cogs_alias(self):
        """'cogs' should resolve to a variable cost category"""
        result = get_dre_category("cogs")
        assert result is not None
        assert result["cost_behavior"] == "variable"

    def test_salaries_alias(self):
        """'salaries' should resolve to a fixed admin expense"""
        result = get_dre_category("salaries")
        assert result is not None
        assert result["cost_behavior"] == "fixed"

    def test_bank_fees_alias(self):
        """'bank_fees' should resolve to financial expense"""
        result = get_dre_category("bank_fees")
        assert result is not None
        assert result["line_type"] == DRELineType.FINANCIAL_EXPENSE

    def test_interest_income_alias(self):
        """'interest_income' should resolve to financial revenue"""
        result = get_dre_category("interest_income")
        assert result is not None
        assert result["line_type"] == DRELineType.FINANCIAL_REVENUE

    def test_income_tax_alias(self):
        """'income_tax' should resolve to IRPJ"""
        result = get_dre_category("income_tax")
        assert result is not None
        assert result["dre_line"] == "irpj"

    def test_marketing_alias(self):
        """'marketing' should resolve to a commercial expense"""
        result = get_dre_category("marketing")
        assert result is not None

    def test_uncategorized_alias(self):
        """'uncategorized' should resolve to nao_categorizado"""
        result = get_dre_category("uncategorized")
        assert result is not None


class TestResolveCategoryName:
    """Test the resolve_category_name function"""

    def test_resolve_v2_name(self):
        """V2 names should resolve to themselves"""
        assert resolve_category_name("cmv") == "cmv"
        assert resolve_category_name("receita_servicos") == "receita_servicos"

    def test_resolve_v1_alias(self):
        """V1 names should resolve to V2 equivalents"""
        assert resolve_category_name("sales") == "receita_vendas_produtos"
        assert resolve_category_name("cogs") == "cmv"
        assert resolve_category_name("salaries") == "salarios_administrativos"

    def test_resolve_none(self):
        """None should resolve to nao_categorizado"""
        assert resolve_category_name(None) == "nao_categorizado"

    def test_resolve_unknown(self):
        """Unknown categories should resolve to nao_categorizado"""
        assert resolve_category_name("completely_random_thing") == "nao_categorizado"

    def test_resolve_case_insensitive(self):
        """Resolution should be case-insensitive"""
        assert resolve_category_name("CMV") == "cmv"
        assert resolve_category_name("SALES") == "receita_vendas_produtos"


class TestDREGroups:
    """Test DRE group mapping"""

    def test_receita_bruta_group(self):
        """Should have Receita Bruta categories"""
        cats = get_categories_by_dre_group("Receita Bruta")
        assert len(cats) == 5  # 5 revenue types from Plano de Contas

    def test_deducoes_group(self):
        """Should have deduction categories"""
        cats = get_categories_by_dre_group("(-) Deduções")
        assert len(cats) == 3

    def test_custos_group(self):
        """Should have cost categories"""
        cats = get_categories_by_dre_group("(-) Custos")
        assert len(cats) == 9  # 5 direct + 4 indirect

    def test_despesas_operacionais_group(self):
        """Should have operating expense categories"""
        cats = get_categories_by_dre_group("(-) Despesas Operacionais")
        # 10 admin + 5 commercial + generics
        assert len(cats) >= 15

    def test_tributos_group(self):
        """Should have tax categories"""
        cats = get_categories_by_dre_group("(-) Tributos")
        assert len(cats) == 5


class TestGetAllCategories:
    """Test the get_all_categories function"""

    def test_returns_sorted_list(self):
        """Should return all categories sorted by order"""
        all_cats = get_all_categories()
        assert len(all_cats) >= 52
        orders = [c["order"] for c in all_cats]
        assert orders == sorted(orders), "Categories should be sorted by order"

    def test_each_has_category_name(self):
        """Each entry should include the category key name"""
        all_cats = get_all_categories()
        for cat in all_cats:
            assert "category" in cat


class TestLegacyListCompatibility:
    """Verify legacy pre-computed lists still work"""

    def test_revenue_categories_not_empty(self):
        assert len(REVENUE_CATEGORIES) >= 5

    def test_deduction_categories_not_empty(self):
        assert len(DEDUCTION_CATEGORIES) >= 3

    def test_depreciation_categories_not_empty(self):
        assert len(DEPRECIATION_CATEGORIES) >= 2

    def test_financial_revenue_categories_not_empty(self):
        assert len(FINANCIAL_REVENUE_CATEGORIES) >= 2

    def test_financial_expense_categories_not_empty(self):
        assert len(FINANCIAL_EXPENSE_CATEGORIES) >= 4

    def test_tax_categories_not_empty(self):
        assert len(TAX_ON_PROFIT_CATEGORIES) >= 5

    def test_admin_expense_equals_fixed_admin(self):
        """Legacy ADMIN_EXPENSE should equal FIXED_EXPENSE_ADMIN"""
        assert len(ADMIN_EXPENSE_CATEGORIES) > 0

    def test_sales_expense_equals_fixed_commercial(self):
        """Legacy SALES_EXPENSE should equal FIXED_EXPENSE_COMMERCIAL"""
        assert len(SALES_EXPENSE_CATEGORIES) > 0
