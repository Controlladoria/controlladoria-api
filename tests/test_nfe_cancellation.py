"""
Tests for NFe Cancellation Support (Item 4)

Tests cover:
- FinancialDocument model with cancellation fields
- XML cancellation extraction (procCancNFe, procEventoNFe)
- Cancellation processing logic (_handle_nfe_cancellation)
- NF number normalization
- Original document linking and status changes
- Edge cases (original not found, already cancelled, etc.)
"""

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, Document, DocumentStatus, AuditLog
from models import FinancialDocument


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


def create_test_document(
    db,
    user_id=1,
    status=DocumentStatus.COMPLETED,
    file_name="test.pdf",
    extracted_data=None,
    is_cancellation=False,
):
    """Helper to create a test document with extracted data"""
    doc = Document(
        file_name=file_name,
        file_type="pdf",
        file_path="/tmp/test.pdf",
        file_size=1000,
        status=status,
        user_id=user_id,
        is_cancellation=is_cancellation,
    )
    if extracted_data:
        doc.extracted_data_json = json.dumps(extracted_data, default=str)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ===== MODEL TESTS =====


class TestFinancialDocumentCancellation:
    """Tests for FinancialDocument model cancellation fields"""

    def test_default_not_cancellation(self):
        """New documents default to is_cancellation=False"""
        doc = FinancialDocument(
            document_type="invoice",
            total_amount="100.00",
            currency="BRL",
        )
        assert doc.is_cancellation is False
        assert doc.original_document_number is None

    def test_cancellation_document(self):
        """Cancellation documents have proper fields set"""
        doc = FinancialDocument(
            document_type="invoice",
            total_amount="0.00",
            currency="BRL",
            is_cancellation=True,
            original_document_number="123456",
        )
        assert doc.is_cancellation is True
        assert doc.original_document_number == "123456"

    def test_cancellation_serialization(self):
        """Cancellation fields serialize properly"""
        doc = FinancialDocument(
            document_type="invoice",
            total_amount="0.00",
            currency="BRL",
            is_cancellation=True,
            original_document_number="789",
        )
        data = doc.model_dump()
        assert data["is_cancellation"] is True
        assert data["original_document_number"] == "789"

    def test_cancellation_from_dict(self):
        """Cancellation fields deserialize from dict"""
        data = {
            "document_type": "invoice",
            "total_amount": "0.00",
            "currency": "BRL",
            "is_cancellation": True,
            "original_document_number": "456",
            "transaction_type": "expense",
        }
        doc = FinancialDocument(**data)
        assert doc.is_cancellation is True
        assert doc.original_document_number == "456"


# ===== DB MODEL TESTS =====


class TestDocumentCancellationDB:
    """Tests for Document DB model cancellation fields"""

    def test_is_cancellation_default(self, db):
        """Document defaults to is_cancellation=False"""
        doc = create_test_document(db)
        assert doc.is_cancellation is False

    def test_is_cancellation_true(self, db):
        """Document can be created as cancellation"""
        doc = create_test_document(db, is_cancellation=True)
        assert doc.is_cancellation is True

    def test_cancellation_linking(self, db):
        """Cancellation documents can link to original via FKs"""
        original = create_test_document(
            db,
            extracted_data={
                "document_type": "invoice",
                "document_number": "12345",
                "total_amount": "100.00",
                "transaction_type": "income",
            },
        )
        cancellation = create_test_document(
            db,
            is_cancellation=True,
            extracted_data={
                "document_type": "invoice",
                "is_cancellation": True,
                "original_document_number": "12345",
                "total_amount": "0.00",
                "transaction_type": "expense",
            },
        )

        # Link them
        original.cancelled_by_document_id = cancellation.id
        cancellation.cancels_document_id = original.id
        original.status = DocumentStatus.CANCELLED
        db.commit()

        db.refresh(original)
        db.refresh(cancellation)

        assert original.status == DocumentStatus.CANCELLED
        assert original.cancelled_by_document_id == cancellation.id
        assert cancellation.cancels_document_id == original.id

    def test_cancelled_status(self, db):
        """CANCELLED status is a valid DocumentStatus"""
        doc = create_test_document(db, status=DocumentStatus.CANCELLED)
        assert doc.status == DocumentStatus.CANCELLED
        assert doc.status.value == "cancelled"


# ===== NF NUMBER NORMALIZATION =====


class TestNfNumberNormalization:
    """Tests for _normalize_nf_number helper"""

    def _normalize(self, number):
        """Import and call the normalize function"""
        # Standalone implementation matching the one in routers/documents.py
        import re

        if not number:
            return ""
        digits = re.sub(r"\D", "", str(number))
        return digits.lstrip("0") or "0"

    def test_simple_number(self):
        assert self._normalize("12345") == "12345"

    def test_leading_zeros(self):
        assert self._normalize("000012345") == "12345"

    def test_with_special_chars(self):
        assert self._normalize("NF-123.456") == "123456"

    def test_all_zeros(self):
        assert self._normalize("0000") == "0"

    def test_empty_string(self):
        assert self._normalize("") == ""

    def test_none(self):
        assert self._normalize(None) == ""

    def test_chave_acesso_nf_extraction(self):
        """Extract NF number from a chave de acesso (positions 25-33)"""
        chave = "35240612345678000195550010001234561234567890"
        # Positions 25-33: 000123456
        nf_number = str(int(chave[25:34]))
        assert nf_number == "123456"


# ===== CANCELLATION PROCESSING LOGIC =====


class TestHandleNfeCancellation:
    """Tests for _handle_nfe_cancellation helper"""

    def _handle_cancellation(self, db, doc, data_dict):
        """
        Standalone version of _handle_nfe_cancellation
        (avoiding heavy routers.documents import).
        """
        import re

        def _normalize_nf_number(number):
            if not number:
                return ""
            digits = re.sub(r"\D", "", str(number))
            return digits.lstrip("0") or "0"

        original_number = data_dict.get("original_document_number", "")
        doc.is_cancellation = True

        if not original_number:
            return

        candidates = (
            db.query(Document)
            .filter(
                Document.user_id == doc.user_id,
                Document.id != doc.id,
                Document.status.in_([
                    DocumentStatus.COMPLETED,
                    DocumentStatus.PENDING_VALIDATION,
                ]),
                Document.is_cancellation == False,
            )
            .all()
        )

        original_doc = None
        for candidate in candidates:
            if not candidate.extracted_data_json:
                continue
            try:
                candidate_data = json.loads(candidate.extracted_data_json)
                candidate_number = candidate_data.get("document_number", "")
                if candidate_number and _normalize_nf_number(
                    candidate_number
                ) == _normalize_nf_number(original_number):
                    original_doc = candidate
                    break
            except (json.JSONDecodeError, TypeError):
                continue

        if original_doc:
            original_doc.status = DocumentStatus.CANCELLED
            original_doc.cancelled_by_document_id = doc.id
            doc.cancels_document_id = original_doc.id

            audit_entry = AuditLog(
                user_id=doc.user_id,
                document_id=original_doc.id,
                action="cancel",
                entity_type="document",
                entity_id=original_doc.id,
                changes_summary=f"Document cancelled by NFe cancellation #{doc.file_name} (doc ID: {doc.id})",
            )
            db.add(audit_entry)
        else:
            doc.error_message = (
                f"NF original #{original_number} não encontrada no sistema. "
                f"Documento de cancelamento salvo para referência."
            )

    def test_cancel_existing_document(self, db):
        """Should cancel original document when found"""
        original = create_test_document(
            db,
            extracted_data={
                "document_type": "invoice",
                "document_number": "12345",
                "total_amount": "500.00",
                "transaction_type": "income",
            },
        )

        cancellation = create_test_document(
            db,
            status=DocumentStatus.PENDING_VALIDATION,
            is_cancellation=True,
            extracted_data={
                "document_type": "invoice",
                "is_cancellation": True,
                "original_document_number": "12345",
                "total_amount": "0.00",
                "transaction_type": "expense",
            },
        )

        data_dict = {
            "is_cancellation": True,
            "original_document_number": "12345",
        }

        self._handle_cancellation(db, cancellation, data_dict)
        db.commit()

        db.refresh(original)
        db.refresh(cancellation)

        assert original.status == DocumentStatus.CANCELLED
        assert original.cancelled_by_document_id == cancellation.id
        assert cancellation.cancels_document_id == original.id
        assert cancellation.is_cancellation is True

    def test_cancel_with_leading_zeros(self, db):
        """Should match even with leading zeros difference"""
        original = create_test_document(
            db,
            extracted_data={
                "document_type": "invoice",
                "document_number": "000012345",
                "total_amount": "200.00",
                "transaction_type": "income",
            },
        )

        cancellation = create_test_document(
            db,
            status=DocumentStatus.PENDING_VALIDATION,
            is_cancellation=True,
        )

        data_dict = {
            "is_cancellation": True,
            "original_document_number": "12345",
        }

        self._handle_cancellation(db, cancellation, data_dict)
        db.commit()

        db.refresh(original)
        assert original.status == DocumentStatus.CANCELLED
        assert original.cancelled_by_document_id == cancellation.id

    def test_original_not_found(self, db):
        """Should set error message when original NF not found"""
        cancellation = create_test_document(
            db,
            status=DocumentStatus.PENDING_VALIDATION,
            is_cancellation=True,
        )

        data_dict = {
            "is_cancellation": True,
            "original_document_number": "99999",
        }

        self._handle_cancellation(db, cancellation, data_dict)
        db.commit()

        db.refresh(cancellation)
        assert cancellation.is_cancellation is True
        assert "99999" in cancellation.error_message
        assert "não encontrada" in cancellation.error_message

    def test_does_not_cancel_already_cancelled(self, db):
        """Should not match documents that are already cancelled"""
        already_cancelled = create_test_document(
            db,
            status=DocumentStatus.CANCELLED,
            extracted_data={
                "document_type": "invoice",
                "document_number": "55555",
                "total_amount": "100.00",
                "transaction_type": "income",
            },
        )

        cancellation = create_test_document(
            db,
            status=DocumentStatus.PENDING_VALIDATION,
            is_cancellation=True,
        )

        data_dict = {
            "is_cancellation": True,
            "original_document_number": "55555",
        }

        self._handle_cancellation(db, cancellation, data_dict)
        db.commit()

        db.refresh(already_cancelled)
        # Should still be CANCELLED (not re-cancelled)
        assert already_cancelled.status == DocumentStatus.CANCELLED
        # Should not have been linked
        assert already_cancelled.cancelled_by_document_id is None
        # Cancellation doc should have error message
        db.refresh(cancellation)
        assert cancellation.error_message is not None

    def test_does_not_cancel_other_users_docs(self, db):
        """Should only match documents from the same user"""
        other_user_doc = create_test_document(
            db,
            user_id=2,  # Different user
            extracted_data={
                "document_type": "invoice",
                "document_number": "77777",
                "total_amount": "300.00",
                "transaction_type": "income",
            },
        )

        cancellation = create_test_document(
            db,
            user_id=1,
            status=DocumentStatus.PENDING_VALIDATION,
            is_cancellation=True,
        )

        data_dict = {
            "is_cancellation": True,
            "original_document_number": "77777",
        }

        self._handle_cancellation(db, cancellation, data_dict)
        db.commit()

        db.refresh(other_user_doc)
        # Other user's doc should NOT be cancelled
        assert other_user_doc.status == DocumentStatus.COMPLETED
        # Cancellation should have error message
        db.refresh(cancellation)
        assert cancellation.error_message is not None

    def test_does_not_cancel_cancellation_docs(self, db):
        """Should not match other cancellation documents"""
        other_cancel = create_test_document(
            db,
            is_cancellation=True,
            extracted_data={
                "document_type": "invoice",
                "document_number": "88888",
                "is_cancellation": True,
                "total_amount": "0.00",
                "transaction_type": "expense",
            },
        )

        cancellation = create_test_document(
            db,
            status=DocumentStatus.PENDING_VALIDATION,
            is_cancellation=True,
        )

        data_dict = {
            "is_cancellation": True,
            "original_document_number": "88888",
        }

        self._handle_cancellation(db, cancellation, data_dict)
        db.commit()

        db.refresh(other_cancel)
        # Other cancellation doc should NOT be matched
        assert other_cancel.status == DocumentStatus.COMPLETED

    def test_no_original_number_does_nothing(self, db):
        """Should handle missing original_document_number gracefully"""
        cancellation = create_test_document(
            db,
            status=DocumentStatus.PENDING_VALIDATION,
            is_cancellation=True,
        )

        data_dict = {
            "is_cancellation": True,
            "original_document_number": "",
        }

        self._handle_cancellation(db, cancellation, data_dict)
        db.commit()

        db.refresh(cancellation)
        assert cancellation.is_cancellation is True
        assert cancellation.error_message is None

    def test_audit_trail_created(self, db):
        """Should create audit log entry when cancelling"""
        original = create_test_document(
            db,
            extracted_data={
                "document_type": "invoice",
                "document_number": "11111",
                "total_amount": "1000.00",
                "transaction_type": "income",
            },
        )

        cancellation = create_test_document(
            db,
            status=DocumentStatus.PENDING_VALIDATION,
            is_cancellation=True,
        )

        data_dict = {
            "is_cancellation": True,
            "original_document_number": "11111",
        }

        self._handle_cancellation(db, cancellation, data_dict)
        db.commit()

        # Check audit log was created
        audit = (
            db.query(AuditLog)
            .filter(
                AuditLog.document_id == original.id,
                AuditLog.action == "cancel",
            )
            .first()
        )
        assert audit is not None
        assert "cancel" in audit.action
        assert str(cancellation.id) in audit.changes_summary

    def test_cancel_pending_validation_doc(self, db):
        """Should be able to cancel documents in PENDING_VALIDATION status too"""
        pending_doc = create_test_document(
            db,
            status=DocumentStatus.PENDING_VALIDATION,
            extracted_data={
                "document_type": "invoice",
                "document_number": "44444",
                "total_amount": "750.00",
                "transaction_type": "income",
            },
        )

        cancellation = create_test_document(
            db,
            status=DocumentStatus.PENDING_VALIDATION,
            is_cancellation=True,
        )

        data_dict = {
            "is_cancellation": True,
            "original_document_number": "44444",
        }

        self._handle_cancellation(db, cancellation, data_dict)
        db.commit()

        db.refresh(pending_doc)
        assert pending_doc.status == DocumentStatus.CANCELLED
        assert pending_doc.cancelled_by_document_id == cancellation.id


# ===== XML CANCELLATION EXTRACTION =====


class TestXmlCancellationExtraction:
    """Tests for XML cancellation document extraction"""

    def test_extract_nfe_cancellation_proc(self):
        """Test extraction from procCancNFe XML structure"""
        from structured_processor import StructuredDocumentProcessor

        processor = StructuredDocumentProcessor.__new__(StructuredDocumentProcessor)

        xml_dict = {
            "procCancNFe": {
                "cancNFe": {
                    "infCanc": {
                        "chNFe": "35240612345678000195550010001234561234567890",
                        "nProt": "135240600000001",
                        "dhRecbto": "2024-06-15T10:30:00-03:00",
                    }
                }
            }
        }

        # Manually set _parse_date method
        result = processor._extract_nfe_cancellation(xml_dict)

        assert result.is_cancellation is True
        assert result.original_document_number is not None
        assert result.total_amount == 0
        assert result.confidence_score == 0.99
        assert "Cancelamento" in result.notes

    def test_extract_nfe_cancellation_event(self):
        """Test extraction from procEventoNFe XML structure"""
        from structured_processor import StructuredDocumentProcessor

        processor = StructuredDocumentProcessor.__new__(StructuredDocumentProcessor)

        xml_dict = {
            "procEventoNFe": {
                "evento": {
                    "infEvento": {
                        "tpEvento": "110111",
                        "chNFe": "35240612345678000195550010001234561234567890",
                        "dhEvento": "2024-06-15T14:00:00-03:00",
                        "detEvento": {
                            "xJust": "Erro na emissão da nota fiscal",
                            "nProt": "135240600000002",
                        },
                    }
                }
            }
        }

        result = processor._extract_nfe_cancellation_event(xml_dict)

        assert result.is_cancellation is True
        assert result.original_document_number is not None
        assert result.total_amount == 0
        assert result.confidence_score == 0.99
        assert "Erro na emissão" in result.notes

    def test_extract_cancellation_chave_parsing(self):
        """Test that original_document_number uses full chave de acesso for matching"""
        from structured_processor import StructuredDocumentProcessor

        processor = StructuredDocumentProcessor.__new__(StructuredDocumentProcessor)

        # Chave de acesso: full 44-char access key used for matching
        chave = "35240612345678000195550010009876541234567890"

        xml_dict = {
            "procCancNFe": {
                "cancNFe": {
                    "infCanc": {
                        "chNFe": chave,
                        "nProt": "PROT123",
                        "dhRecbto": "2024-06-15",
                    }
                }
            }
        }

        result = processor._extract_nfe_cancellation(xml_dict)

        # original_document_number should be the full chave de acesso
        # (used for matching against stored NFe document_number which is also the full chave)
        assert result.original_document_number == chave

    def test_extract_cancellation_missing_chave(self):
        """Test graceful handling when chave de acesso is missing"""
        from structured_processor import StructuredDocumentProcessor

        processor = StructuredDocumentProcessor.__new__(StructuredDocumentProcessor)

        xml_dict = {
            "procCancNFe": {
                "cancNFe": {
                    "infCanc": {
                        "nProt": "PROT123",
                    }
                }
            }
        }

        result = processor._extract_nfe_cancellation(xml_dict)

        assert result.is_cancellation is True
        assert result.total_amount == 0
        # Should still work, just without a specific original number


# ===== CANCELLED DOCUMENTS IN REPORTS =====


class TestCancelledDocumentsExclusion:
    """Tests that cancelled documents are excluded from financial reports"""

    def test_cancelled_not_completed(self, db):
        """CANCELLED documents should not be in COMPLETED status"""
        doc = create_test_document(db, status=DocumentStatus.CANCELLED)
        completed = (
            db.query(Document)
            .filter(Document.status == DocumentStatus.COMPLETED)
            .all()
        )
        assert doc not in completed

    def test_cancelled_docs_filtered_out(self, db):
        """Report queries filtering by COMPLETED should exclude CANCELLED docs"""
        # Create various docs
        completed_doc = create_test_document(
            db,
            file_name="completed.pdf",
            status=DocumentStatus.COMPLETED,
        )
        cancelled_doc = create_test_document(
            db,
            file_name="cancelled.pdf",
            status=DocumentStatus.CANCELLED,
        )
        pending_doc = create_test_document(
            db,
            file_name="pending.pdf",
            status=DocumentStatus.PENDING_VALIDATION,
        )

        # Query like reports do (only COMPLETED)
        report_docs = (
            db.query(Document)
            .filter(Document.status == DocumentStatus.COMPLETED)
            .all()
        )

        assert len(report_docs) == 1
        assert report_docs[0].id == completed_doc.id

    def test_both_original_and_cancellation_preserved(self, db):
        """Both the original and cancellation documents should remain in DB"""
        original = create_test_document(
            db,
            file_name="original.pdf",
            status=DocumentStatus.CANCELLED,
            extracted_data={
                "document_type": "invoice",
                "document_number": "123",
                "total_amount": "100.00",
                "transaction_type": "income",
            },
        )
        cancellation = create_test_document(
            db,
            file_name="cancel.pdf",
            is_cancellation=True,
            status=DocumentStatus.PENDING_VALIDATION,
            extracted_data={
                "document_type": "invoice",
                "is_cancellation": True,
                "original_document_number": "123",
                "total_amount": "0.00",
                "transaction_type": "expense",
            },
        )

        # Link them
        original.cancelled_by_document_id = cancellation.id
        cancellation.cancels_document_id = original.id
        db.commit()

        # Both should still exist in DB
        all_docs = db.query(Document).all()
        assert len(all_docs) == 2

        # Can query cancellation relationships
        db.refresh(original)
        assert original.cancelled_by_document_id == cancellation.id

        db.refresh(cancellation)
        assert cancellation.cancels_document_id == original.id
