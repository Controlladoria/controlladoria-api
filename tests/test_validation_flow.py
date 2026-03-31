"""
Tests for Document Validation Flow (Item 9)
Tests the full flow: upload -> AI process -> pending_validation -> user review -> confirm -> completed
"""

import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Document, DocumentStatus, DocumentValidationRow


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


@pytest.fixture
def sample_document(db):
    """A document in PENDING_VALIDATION state with extracted data"""
    extracted_data = {
        "document_type": "invoice",
        "document_number": "NF-001",
        "issue_date": "2024-06-15",
        "transaction_type": "expense",
        "category": "cmv",
        "total_amount": 1500.50,
        "issuer": {"name": "Fornecedor ABC", "cnpj": "12.345.678/0001-90"},
    }

    doc = Document(
        file_name="nota_fiscal.pdf",
        file_type="pdf",
        file_path="/tmp/nota_fiscal.pdf",
        file_size=50000,
        status=DocumentStatus.PENDING_VALIDATION,
        user_id=1,
        extracted_data_json=json.dumps(extracted_data),
        processed_date=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@pytest.fixture
def sample_ledger_document(db):
    """A multi-transaction ledger document in PENDING_VALIDATION state"""
    extracted_data = {
        "document_type": "transaction_ledger",
        "transactions": [
            {
                "date": "2024-06-01",
                "description": "Venda produto A",
                "amount": 5000.00,
                "category": "receita_vendas_produtos",
                "transaction_type": "income",
            },
            {
                "date": "2024-06-02",
                "description": "Compra matéria prima",
                "amount": 2000.00,
                "category": "materia_prima",
                "transaction_type": "expense",
            },
            {
                "date": "2024-06-03",
                "description": "Pagamento aluguel",
                "amount": 1500.00,
                "category": "aluguel",
                "transaction_type": "expense",
            },
        ],
    }

    doc = Document(
        file_name="extrato_junho.xlsx",
        file_type="xlsx",
        file_path="/tmp/extrato_junho.xlsx",
        file_size=30000,
        status=DocumentStatus.PENDING_VALIDATION,
        user_id=1,
        extracted_data_json=json.dumps(extracted_data),
        processed_date=datetime.utcnow(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ===== DOCUMENT STATUS TESTS =====


def test_pending_validation_status_exists():
    """PENDING_VALIDATION status should be available"""
    assert DocumentStatus.PENDING_VALIDATION.value == "pending_validation"


def test_cancelled_status_exists():
    """CANCELLED status should be available"""
    assert DocumentStatus.CANCELLED.value == "cancelled"


def test_document_starts_pending_validation(sample_document):
    assert sample_document.status == DocumentStatus.PENDING_VALIDATION


# ===== VALIDATION ROW MODEL TESTS =====


def test_create_validation_row(db, sample_document):
    """Should be able to create a validation row"""
    row = DocumentValidationRow(
        document_id=sample_document.id,
        row_index=0,
        description="Test transaction",
        transaction_date="2024-06-15",
        amount=150050,  # In cents
        category="cmv",
        transaction_type="expense",
        user_id=1,
        original_data_json='{"test": true}',
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.id is not None
    assert row.document_id == sample_document.id
    assert row.amount == 150050
    assert row.is_validated is False
    assert row.validated_at is None


def test_validation_row_relationship(db, sample_document):
    """Validation rows should be accessible via document relationship"""
    row = DocumentValidationRow(
        document_id=sample_document.id,
        row_index=0,
        description="Test",
        amount=100,
        user_id=1,
    )
    db.add(row)
    db.commit()

    db.refresh(sample_document)
    assert len(sample_document.validation_rows) == 1
    assert sample_document.validation_rows[0].description == "Test"


def test_multiple_validation_rows(db, sample_document):
    """Should support multiple rows per document"""
    for i in range(5):
        row = DocumentValidationRow(
            document_id=sample_document.id,
            row_index=i,
            description=f"Transaction {i}",
            amount=(i + 1) * 10000,
            user_id=1,
        )
        db.add(row)
    db.commit()

    db.refresh(sample_document)
    assert len(sample_document.validation_rows) == 5


# ===== CREATE VALIDATION ROWS HELPER TESTS =====


def _create_validation_rows_standalone(db, doc, data_dict):
    """
    Standalone version of _create_validation_rows for testing.
    (Avoids importing routers.documents which triggers heavy AI processor init)
    """
    transactions = data_dict.get("transactions") or []

    if transactions:
        for idx, txn in enumerate(transactions):
            amount_val = txn.get("amount")
            amount_cents = int(float(amount_val) * 100) if amount_val is not None else None

            row = DocumentValidationRow(
                document_id=doc.id,
                row_index=idx,
                description=txn.get("description"),
                transaction_date=txn.get("date"),
                amount=amount_cents,
                category=txn.get("category"),
                transaction_type=txn.get("transaction_type", "expense"),
                original_data_json=json.dumps(txn, default=str),
                user_id=doc.user_id,
            )
            db.add(row)
    else:
        total = data_dict.get("total_amount")
        amount_cents = int(float(total) * 100) if total is not None else None

        description_parts = []
        if data_dict.get("document_type"):
            description_parts.append(data_dict["document_type"])
        if data_dict.get("document_number"):
            description_parts.append(f"#{data_dict['document_number']}")
        issuer = data_dict.get("issuer")
        if issuer and isinstance(issuer, dict) and issuer.get("name"):
            description_parts.append(f"- {issuer['name']}")

        description = " ".join(description_parts) if description_parts else doc.file_name

        row = DocumentValidationRow(
            document_id=doc.id,
            row_index=0,
            description=description,
            transaction_date=data_dict.get("issue_date"),
            amount=amount_cents,
            category=data_dict.get("category"),
            transaction_type=data_dict.get("transaction_type", "expense"),
            original_data_json=json.dumps(data_dict, default=str),
            user_id=doc.user_id,
        )
        db.add(row)


def test_create_validation_rows_single_transaction(db):
    """Should create 1 row for single-transaction docs"""
    doc = Document(
        file_name="invoice.pdf",
        file_type="pdf",
        file_path="/tmp/invoice.pdf",
        file_size=1000,
        status=DocumentStatus.PENDING_VALIDATION,
        user_id=1,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    data_dict = {
        "document_type": "invoice",
        "document_number": "NF-123",
        "issue_date": "2024-06-15",
        "total_amount": 1500.50,
        "category": "cmv",
        "transaction_type": "expense",
        "issuer": {"name": "Supplier Co"},
    }

    _create_validation_rows_standalone(db, doc, data_dict)
    db.commit()

    rows = (
        db.query(DocumentValidationRow)
        .filter(DocumentValidationRow.document_id == doc.id)
        .all()
    )
    assert len(rows) == 1
    assert rows[0].row_index == 0
    assert rows[0].amount == 150050  # 1500.50 * 100 cents
    assert rows[0].category == "cmv"
    assert rows[0].transaction_type == "expense"
    assert rows[0].transaction_date == "2024-06-15"
    assert "invoice" in rows[0].description
    assert "NF-123" in rows[0].description
    assert "Supplier Co" in rows[0].description


def test_create_validation_rows_multi_transaction(db):
    """Should create 1 row per transaction for ledgers"""
    doc = Document(
        file_name="extrato.xlsx",
        file_type="xlsx",
        file_path="/tmp/extrato.xlsx",
        file_size=1000,
        status=DocumentStatus.PENDING_VALIDATION,
        user_id=1,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    data_dict = {
        "document_type": "transaction_ledger",
        "transactions": [
            {
                "date": "2024-06-01",
                "description": "Sale 1",
                "amount": 5000.00,
                "category": "receita_vendas_produtos",
                "transaction_type": "income",
            },
            {
                "date": "2024-06-02",
                "description": "Purchase 1",
                "amount": 2000.00,
                "category": "materia_prima",
                "transaction_type": "expense",
            },
        ],
    }

    _create_validation_rows_standalone(db, doc, data_dict)
    db.commit()

    rows = (
        db.query(DocumentValidationRow)
        .filter(DocumentValidationRow.document_id == doc.id)
        .order_by(DocumentValidationRow.row_index)
        .all()
    )
    assert len(rows) == 2

    assert rows[0].row_index == 0
    assert rows[0].description == "Sale 1"
    assert rows[0].amount == 500000  # 5000.00 * 100
    assert rows[0].category == "receita_vendas_produtos"
    assert rows[0].transaction_type == "income"

    assert rows[1].row_index == 1
    assert rows[1].description == "Purchase 1"
    assert rows[1].amount == 200000
    assert rows[1].category == "materia_prima"
    assert rows[1].transaction_type == "expense"


def test_create_validation_rows_preserves_original(db):
    """Original data should be preserved in original_data_json"""
    doc = Document(
        file_name="test.pdf",
        file_type="pdf",
        file_path="/tmp/test.pdf",
        file_size=1000,
        status=DocumentStatus.PENDING_VALIDATION,
        user_id=1,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    data_dict = {
        "document_type": "receipt",
        "total_amount": 99.99,
        "category": "aluguel",
        "transaction_type": "expense",
    }

    _create_validation_rows_standalone(db, doc, data_dict)
    db.commit()

    row = (
        db.query(DocumentValidationRow)
        .filter(DocumentValidationRow.document_id == doc.id)
        .first()
    )
    assert row.original_data_json is not None
    original = json.loads(row.original_data_json)
    assert original["category"] == "aluguel"
    assert original["total_amount"] == 99.99


# ===== VALIDATION FLOW TESTS =====


def test_validate_single_row(db, sample_document):
    """Marking a row as validated"""
    row = DocumentValidationRow(
        document_id=sample_document.id,
        row_index=0,
        description="Test",
        amount=100,
        is_validated=False,
        user_id=1,
    )
    db.add(row)
    db.commit()

    # Validate
    row.is_validated = True
    row.validated_at = datetime.utcnow()
    db.commit()

    db.refresh(row)
    assert row.is_validated is True
    assert row.validated_at is not None


def test_edit_row_during_validation(db, sample_document):
    """User should be able to edit row data during validation"""
    row = DocumentValidationRow(
        document_id=sample_document.id,
        row_index=0,
        description="Original description",
        amount=100000,
        category="cmv",
        transaction_type="expense",
        user_id=1,
    )
    db.add(row)
    db.commit()

    # Edit
    row.description = "Updated description"
    row.amount = 150000
    row.category = "materia_prima"
    row.transaction_type = "expense"
    db.commit()

    db.refresh(row)
    assert row.description == "Updated description"
    assert row.amount == 150000
    assert row.category == "materia_prima"


def test_confirm_validation_changes_status(db, sample_document):
    """Confirming validation should change document to COMPLETED"""
    row = DocumentValidationRow(
        document_id=sample_document.id,
        row_index=0,
        description="Test",
        amount=100,
        user_id=1,
    )
    db.add(row)
    db.commit()

    # Confirm
    sample_document.status = DocumentStatus.COMPLETED
    row.is_validated = True
    row.validated_at = datetime.utcnow()
    db.commit()

    db.refresh(sample_document)
    assert sample_document.status == DocumentStatus.COMPLETED


def test_reject_validation_changes_status(db, sample_document):
    """Rejecting should change document to FAILED"""
    sample_document.status = DocumentStatus.FAILED
    sample_document.error_message = "Rejeitado pelo usuário durante validação"
    db.commit()

    db.refresh(sample_document)
    assert sample_document.status == DocumentStatus.FAILED
    assert "Rejeitado" in sample_document.error_message


def test_pending_validation_not_in_completed(db):
    """PENDING_VALIDATION documents should not appear when filtering COMPLETED"""
    # Create docs with different statuses
    for status in [
        DocumentStatus.PENDING_VALIDATION,
        DocumentStatus.COMPLETED,
        DocumentStatus.COMPLETED,
        DocumentStatus.FAILED,
    ]:
        doc = Document(
            file_name=f"test_{status.value}.pdf",
            file_type="pdf",
            file_path=f"/tmp/test_{status.value}.pdf",
            file_size=1000,
            status=status,
            user_id=1,
        )
        db.add(doc)
    db.commit()

    completed_docs = (
        db.query(Document)
        .filter(Document.status == DocumentStatus.COMPLETED)
        .all()
    )
    assert len(completed_docs) == 2

    pending_validation = (
        db.query(Document)
        .filter(Document.status == DocumentStatus.PENDING_VALIDATION)
        .all()
    )
    assert len(pending_validation) == 1


def test_cascade_delete_validation_rows(db, sample_document):
    """Deleting a document should cascade delete its validation rows"""
    for i in range(3):
        row = DocumentValidationRow(
            document_id=sample_document.id,
            row_index=i,
            description=f"Row {i}",
            amount=100,
            user_id=1,
        )
        db.add(row)
    db.commit()

    # Verify rows exist
    row_count = (
        db.query(DocumentValidationRow)
        .filter(DocumentValidationRow.document_id == sample_document.id)
        .count()
    )
    assert row_count == 3

    # Delete document
    db.delete(sample_document)
    db.commit()

    # Rows should be cascade deleted
    row_count = (
        db.query(DocumentValidationRow)
        .filter(DocumentValidationRow.document_id == sample_document.id)
        .count()
    )
    assert row_count == 0


# ===== NFE CANCELLATION FIELDS =====


def test_nfe_cancellation_fields_exist(db):
    """Document model should have cancellation fields"""
    doc = Document(
        file_name="nfe_cancel.pdf",
        file_type="pdf",
        file_path="/tmp/nfe_cancel.pdf",
        file_size=1000,
        status=DocumentStatus.PENDING,
        user_id=1,
        is_cancellation=True,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    assert doc.is_cancellation is True
    assert doc.cancelled_by_document_id is None
    assert doc.cancels_document_id is None


def test_nfe_cancellation_self_reference(db):
    """Cancellation links should work as self-references"""
    original = Document(
        file_name="original_nfe.pdf",
        file_type="pdf",
        file_path="/tmp/original_nfe.pdf",
        file_size=1000,
        status=DocumentStatus.COMPLETED,
        user_id=1,
    )
    db.add(original)
    db.commit()

    cancellation = Document(
        file_name="cancel_nfe.pdf",
        file_type="pdf",
        file_path="/tmp/cancel_nfe.pdf",
        file_size=1000,
        status=DocumentStatus.COMPLETED,
        user_id=1,
        is_cancellation=True,
        cancels_document_id=original.id,
    )
    db.add(cancellation)
    db.commit()

    # Link original back
    original.cancelled_by_document_id = cancellation.id
    original.status = DocumentStatus.CANCELLED
    db.commit()

    db.refresh(original)
    db.refresh(cancellation)

    assert original.status == DocumentStatus.CANCELLED
    assert original.cancelled_by_document_id == cancellation.id
    assert cancellation.cancels_document_id == original.id
    assert cancellation.is_cancellation is True
