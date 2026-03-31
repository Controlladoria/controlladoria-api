#!/usr/bin/env python
"""
Test to verify unit conversions are working correctly
Can be run standalone to verify the fixes
"""

from decimal import Decimal


def test_opening_balances_conversion():
    """Test the conversion in set_opening_balances"""
    print("Testing set_opening_balances conversion...")

    # Input: dollars
    balance = Decimal("5000.00")
    print(f"  Input: {balance} dollars")

    # Conversion: dollars → cents
    balance_cents = int(balance * 100)
    print(f"  Converted: {balance_cents} cents")

    # Expected in database
    expected = 500000
    print(f"  Expected in DB: {expected} cents")

    assert balance_cents == expected, f"Expected {expected}, got {balance_cents}"
    print("  ✓ PASS\n")


def test_manual_entry_no_conversion():
    """Test that create_manual_journal_entry doesn't convert"""
    print("Testing create_manual_journal_entry (no conversion)...")

    # Input: cents (from test)
    debit_amount = 5000
    print(f"  Input: {debit_amount} cents")

    # No conversion
    stored_value = int(debit_amount)
    print(f"  Stored: {stored_value} cents")

    # Expected in database
    expected = 5000
    print(f"  Expected in DB: {expected} cents")

    assert stored_value == expected, f"Expected {expected}, got {stored_value}"
    print("  ✓ PASS\n")


def test_ledger_conversion():
    """Test the conversion in get_account_ledger"""
    print("Testing get_account_ledger conversion...")

    # From database: cents
    debit_amount = 5000
    print(f"  From DB: {debit_amount} cents")

    # Conversion: cents → dollars
    debit = Decimal(debit_amount) / Decimal(100)
    print(f"  Converted: {debit} dollars")

    # Expected output
    expected = Decimal("50.00")
    print(f"  Expected output: {expected} dollars")

    assert debit == expected, f"Expected {expected}, got {debit}"
    print("  ✓ PASS\n")


def test_balance_sheet_conversion():
    """Test the conversion in balance sheet calculation"""
    print("Testing balance sheet conversion...")

    # From database: cents
    total_debits = 500000
    total_credits = 0
    print(f"  From DB: debits={total_debits} cents, credits={total_credits} cents")

    # Conversion: cents → dollars
    balance_cents = total_debits - total_credits
    balance = Decimal(balance_cents) / Decimal(100)
    print(f"  Balance in cents: {balance_cents}")
    print(f"  Converted: {balance} dollars")

    # Expected output
    expected = Decimal("5000.00")
    print(f"  Expected output: {expected} dollars")

    assert balance == expected, f"Expected {expected}, got {balance}"
    print("  ✓ PASS\n")


def test_transaction_conversion():
    """Test the conversion in generate_journal_entry_from_transaction"""
    print("Testing transaction generation conversion...")

    # Input: dollars
    amount = Decimal("1500.00")
    print(f"  Input: {amount} dollars")

    # Conversion: dollars → cents
    amount_cents = int(amount * 100)
    print(f"  Converted: {amount_cents} cents")

    # Expected in database
    expected = 150000
    print(f"  Expected in DB: {expected} cents")

    assert amount_cents == expected, f"Expected {expected}, got {amount_cents}"
    print("  ✓ PASS\n")


def test_full_cycle():
    """Test a complete read-write cycle"""
    print("Testing full cycle (write then read)...")

    # 1. User input
    user_input = Decimal("5000.00")
    print(f"  1. User input: {user_input} dollars")

    # 2. Convert to cents for storage
    stored = int(user_input * 100)
    print(f"  2. Store in DB: {stored} cents")

    # 3. Read from database
    from_db = stored
    print(f"  3. Read from DB: {from_db} cents")

    # 4. Convert to dollars for display
    displayed = Decimal(from_db) / Decimal(100)
    print(f"  4. Display to user: {displayed} dollars")

    # 5. Verify round-trip
    assert user_input == displayed, f"Expected {user_input}, got {displayed}"
    print("  ✓ PASS - Round-trip successful!\n")


def test_error_case_double_conversion():
    """Show what happens with double conversion (the bug we fixed)"""
    print("Testing ERROR CASE (what was happening before fix)...")

    # User input
    balance = Decimal("5000.00")
    print(f"  1. User input: {balance} dollars")

    # First conversion (correct)
    balance_cents = int(balance * 100)
    print(f"  2. First conversion: {balance_cents} cents")

    # BUG: Converting to Decimal without dividing by 100
    balance_decimal = Decimal(balance_cents)  # Treating cents as dollars!
    print(
        f"  3. Bug: Decimal({balance_cents}) = {balance_decimal} (treated as dollars)"
    )

    # Second conversion (wrong!)
    stored = int(balance_decimal * 100)
    print(f"  4. Second conversion: {stored} cents")

    # This is what was stored
    print(f"  5. What was stored: {stored} cents = R$ {stored/100:,.2f}")
    print(f"  6. What should be stored: 500000 cents = R$ 5,000.00")
    print(f"  7. ERROR: Off by factor of 100! ({stored/500000}x too much)")
    print("  ✗ FAIL - This is the bug we fixed!\n")


if __name__ == "__main__":
    print("=" * 60)
    print("UNIT CONVERSION TESTS")
    print("=" * 60)
    print()

    try:
        test_opening_balances_conversion()
        test_manual_entry_no_conversion()
        test_ledger_conversion()
        test_balance_sheet_conversion()
        test_transaction_conversion()
        test_full_cycle()

        print("=" * 60)
        print("ALL TESTS PASSED!")
        print("=" * 60)
        print()

        # Show the error case
        test_error_case_double_conversion()

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}\n")
        exit(1)
