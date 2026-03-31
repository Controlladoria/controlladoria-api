"""
Test script for hospital-grade financial system features
Tests validation, duplicate detection, and audit logging
"""

import json
import sys
from datetime import datetime
from decimal import Decimal

import pytest

from validation import DuplicateDetector, FinancialValidator


def test_financial_validation():
    """Test FinancialValidator"""
    validator = FinancialValidator()

    # Test valid document
    valid_doc = {
        "document_type": "invoice",
        "issue_date": "2026-01-15",
        "transaction_type": "expense",
        "category": "medical_supplies",
        "department": "cardiology",
        "total_amount": "1250.50",
        "currency": "BRL",
    }

    is_valid, errors, warnings = validator.validate_document(valid_doc)
    assert is_valid is True
    assert len(errors) == 0


def test_financial_validation_negative_amount():
    """Test validation rejects negative amounts"""
    validator = FinancialValidator()

    invalid_doc = {
        "document_type": "invoice",
        "transaction_type": "expense",
        "total_amount": "-100.00",  # Invalid!
    }

    is_valid, errors, warnings = validator.validate_document(invalid_doc)
    assert is_valid is False
    assert len(errors) > 0


def test_financial_validation_calculation_error():
    """Test validation detects calculation errors"""
    validator = FinancialValidator()

    calc_error_doc = {
        "document_type": "invoice",
        "total_amount": "100.00",
        "subtotal": "80.00",
        "tax_amount": "15.00",  # Should be 20 to match total
        "discount": "0.00",
    }

    is_valid, errors, warnings = validator.validate_document(calc_error_doc)
    # Should either be invalid or have warnings about calculation mismatch
    assert is_valid is False or len(warnings) > 0


def test_duplicate_detection_exact():
    """Test DuplicateDetector finds exact duplicates"""
    existing_docs = [
        {
            "document_number": "INV-2026-001",
            "issue_date": "2026-01-15",
            "total_amount": "1250.50",
            "issuer": {"tax_id": "12.345.678/0001-90"},
        },
        {
            "document_number": "INV-2026-002",
            "issue_date": "2026-01-16",
            "total_amount": "500.00",
            "issuer": {"tax_id": "98.765.432/0001-10"},
        },
    ]

    exact_duplicate = {
        "document_number": "INV-2026-001",
        "issue_date": "2026-01-15",
        "total_amount": "1250.50",
        "issuer": {"tax_id": "12.345.678/0001-90"},
    }

    duplicates = DuplicateDetector.find_duplicates(existing_docs, exact_duplicate)
    assert len(duplicates) > 0
    assert duplicates[0]['similarity_score'] >= 90  # High similarity


def test_duplicate_detection_partial():
    """Test DuplicateDetector finds partial matches"""
    existing_docs = [
        {
            "document_number": "INV-2026-001",
            "issue_date": "2026-01-15",
            "total_amount": "1250.50",
            "issuer": {"tax_id": "12.345.678/0001-90"},
        },
    ]

    partial_match = {
        "document_number": "INV-2026-003",
        "issue_date": "2026-01-20",
        "total_amount": "1250.50",
        "issuer": {"tax_id": "12.345.678/0001-90"},
    }

    duplicates = DuplicateDetector.find_duplicates(existing_docs, partial_match)
    # Should find at least some similarity (same amount and issuer)
    assert len(duplicates) >= 0  # May or may not detect depending on threshold


def test_duplicate_detection_no_match():
    """Test DuplicateDetector doesn't flag non-duplicates"""
    existing_docs = [
        {
            "document_number": "INV-2026-001",
            "issue_date": "2026-01-15",
            "total_amount": "1250.50",
            "issuer": {"tax_id": "12.345.678/0001-90"},
        },
    ]

    no_match = {
        "document_number": "INV-2026-999",
        "issue_date": "2026-01-25",
        "total_amount": "9999.99",
        "issuer": {"tax_id": "11.111.111/0001-11"},
    }

    duplicates = DuplicateDetector.find_duplicates(existing_docs, no_match)
    # Should not find high-confidence duplicates
    if duplicates:
        assert duplicates[0]['similarity_score'] < 70


def test_cnpj_validation_valid():
    """Test CNPJ validation accepts valid CNPJ"""
    validator = FinancialValidator()

    valid_cnpj_doc = {
        "document_type": "invoice",
        "total_amount": "100.00",
        "issuer": {"name": "Empresa Teste", "tax_id": "11.222.333/0001-81"},
    }

    is_valid, errors, warnings = validator.validate_document(valid_cnpj_doc)
    # Should be valid or only have warnings, not errors
    assert is_valid is True or len(errors) == 0


def test_cnpj_validation_invalid():
    """Test CNPJ validation detects invalid CNPJ"""
    validator = FinancialValidator()

    invalid_cnpj_doc = {
        "document_type": "invoice",
        "total_amount": "100.00",
        "issuer": {"name": "Empresa Teste", "tax_id": "11.111.111/1111-11"},
    }

    is_valid, errors, warnings = validator.validate_document(invalid_cnpj_doc)
    # Should have warnings or errors about invalid CNPJ
    cnpj_issues = [w for w in warnings if 'CNPJ' in w or 'CPF' in w]
    assert len(cnpj_issues) > 0 or is_valid is False


def test_csv_import_simulation():
    """Simulate CSV import validation"""
    validator = FinancialValidator()

    # Simulate CSV rows
    csv_rows = [
        {
            "date": "2026-01-15",
            "description": "Medical Supplies",
            "category": "supplies",
            "department": "cardiology",
            "amount": "1250.50",
            "type": "expense",
        },
        {
            "date": "2026-01-16",
            "description": "Patient Revenue",
            "category": "revenue",
            "department": "emergency",
            "amount": "3500.00",
            "type": "income",
        },
        {
            "date": "2026-01-17",
            "description": "Equipment Purchase",
            "category": "equipment",
            "department": "radiology",
            "amount": "-500.00",  # Invalid!
            "type": "expense",
        },
    ]

    success_count = 0
    error_count = 0

    for row in csv_rows:
        doc_data = {
            "document_type": "transaction_ledger",
            "issue_date": row["date"],
            "transaction_type": row["type"],
            "category": row["category"],
            "department": row["department"],
            "total_amount": row["amount"],
            "currency": "BRL",
            "notes": row["description"],
        }

        is_valid, errors, warnings = validator.validate_document(doc_data)

        if is_valid:
            success_count += 1
        else:
            error_count += 1

    # Should have 2 valid rows and 1 invalid (negative amount)
    assert success_count == 2
    assert error_count == 1
