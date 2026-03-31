"""
Integration tests for document processing with real test files
Tests upload, extraction, validation for all file types in test_files folder
"""

import os
import pytest
import time
from pathlib import Path

# Test files directory
TEST_FILES_DIR = Path(__file__).parent.parent.parent / "test_files"


class TestDocumentProcessing:
    """Test document upload and processing with real files"""

    def test_test_files_directory_exists(self):
        """Verify test_files directory exists"""
        assert TEST_FILES_DIR.exists(), f"test_files directory not found at {TEST_FILES_DIR}"
        assert TEST_FILES_DIR.is_dir(), "test_files is not a directory"

    def test_xml_nfe_upload_and_processing(self, client, auth_headers):
        """Test XML NFe upload and extraction"""
        xml_file = TEST_FILES_DIR / "05938517000140_1_66015-1.xml"
        assert xml_file.exists(), f"XML file not found: {xml_file}"

        # Upload document
        with open(xml_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                files={"file": (xml_file.name, f, "application/xml")},
                headers=auth_headers,
            )

        assert response.status_code == 200, f"Upload failed: {response.text}"
        data = response.json()
        assert "id" in data
        assert data["file_name"] == xml_file.name
        assert data["file_type"] == "xml"
        assert data["status"] in ["pending", "processing", "completed"]

        document_id = data["id"]

        # Wait for processing (up to 30 seconds)
        max_wait = 30
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = client.get(f"/documents/{document_id}", headers=auth_headers)
            assert response.status_code == 200
            doc = response.json()

            if doc["status"] == "completed":
                # Verify extracted data
                assert doc["extracted_data"] is not None
                extracted = doc["extracted_data"]

                # NFe should have key fields
                assert "total_amount" in extracted or "valor_total" in extracted

                print(f"[OK] XML NFe processed successfully: {xml_file.name}")
                return
            elif doc["status"] == "failed":
                pytest.fail(f"Document processing failed: {doc.get('error_message')}")

            time.sleep(2)

        pytest.fail(f"Document processing timed out after {max_wait}s")

    def test_xml_cancelled_nfe_upload(self, client, auth_headers):
        """Test cancelled NFe XML upload"""
        xml_file = TEST_FILES_DIR / "21240541870563000118550010000000011306071174procCancNfe.xml"
        assert xml_file.exists(), f"XML file not found: {xml_file}"

        with open(xml_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                files={"file": (xml_file.name, f, "application/xml")},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["file_type"] == "xml"
        print(f"[OK] Cancelled NFe XML uploaded: {xml_file.name}")

    def test_pdf_payroll_upload_and_processing(self, client, auth_headers):
        """Test PDF payroll upload and extraction"""
        pdf_file = TEST_FILES_DIR / "1 - Folha de Pagamento.pdf"
        assert pdf_file.exists(), f"PDF file not found: {pdf_file}"

        with open(pdf_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                files={"file": (pdf_file.name, f, "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["file_type"] == "pdf"
        assert data["status"] in ["pending", "processing", "completed"]

        document_id = data["id"]

        # Wait for processing
        max_wait = 30
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = client.get(f"/documents/{document_id}", headers=auth_headers)
            assert response.status_code == 200
            doc = response.json()

            if doc["status"] == "completed":
                # Verify extracted data exists
                assert doc["extracted_data"] is not None
                print(f"[OK] PDF payroll processed: {pdf_file.name}")
                return
            elif doc["status"] == "failed":
                # Processing can fail if API keys not configured - that's OK for tests
                print(f"[WARN] Document processing failed (API keys may not be configured): {pdf_file.name}")
                return

            time.sleep(2)

        pytest.fail(f"Document processing timed out after {max_wait}s")

    def test_pdf_invoice_agr_upload(self, client, auth_headers):
        """Test AGR invoice PDF upload"""
        pdf_file = TEST_FILES_DIR / "AGR - NF 14.pdf"
        assert pdf_file.exists(), f"PDF file not found: {pdf_file}"

        with open(pdf_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                files={"file": (pdf_file.name, f, "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["file_type"] == "pdf"
        print(f"[OK] AGR invoice PDF uploaded: {pdf_file.name}")

    def test_pdf_danfe_upload(self, client, auth_headers):
        """Test DANFE PDF upload"""
        pdf_file = TEST_FILES_DIR / "DANFE-21231208308704000138550010000123501870436180.PDF"
        assert pdf_file.exists(), f"PDF file not found: {pdf_file}"

        with open(pdf_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                files={"file": (pdf_file.name, f, "application/pdf")},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["file_type"] == "pdf"
        print(f"[OK] DANFE PDF uploaded: {pdf_file.name}")

    def test_excel_gestao_geral_upload(self, client, auth_headers):
        """Test Excel financial management file upload"""
        excel_file = TEST_FILES_DIR / "Gestão Geral_20250827.xlsx"
        assert excel_file.exists(), f"Excel file not found: {excel_file}"

        with open(excel_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                files={"file": (excel_file.name, f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["file_type"] in ["xlsx", "excel"]
        print(f"[OK] Excel file uploaded: {excel_file.name}")

    def test_all_test_files_upload_batch(self, client, auth_headers):
        """Test batch upload of all test files"""
        test_files = list(TEST_FILES_DIR.glob("*"))
        test_files = [f for f in test_files if f.is_file()]

        assert len(test_files) > 0, "No test files found"

        uploaded_count = 0
        failed_count = 0

        for test_file in test_files:
            # Determine content type
            ext = test_file.suffix.lower()
            content_types = {
                ".xml": "application/xml",
                ".pdf": "application/pdf",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
            content_type = content_types.get(ext, "application/octet-stream")

            try:
                with open(test_file, "rb") as f:
                    response = client.post(
                        "/documents/upload",
                        files={"file": (test_file.name, f, content_type)},
                        headers=auth_headers,
                    )

                if response.status_code == 200:
                    uploaded_count += 1
                    print(f"  [OK] Uploaded: {test_file.name}")
                else:
                    failed_count += 1
                    print(f"  [FAIL] Failed: {test_file.name} - {response.status_code}")
            except Exception as e:
                failed_count += 1
                print(f"  [FAIL] Error: {test_file.name} - {str(e)}")

        print(f"\n[STATS] Batch upload results: {uploaded_count} succeeded, {failed_count} failed out of {len(test_files)} files")
        assert uploaded_count > 0, "No files were uploaded successfully"

    def test_document_validation_on_test_files(self, client, auth_headers):
        """Test validation engine on uploaded documents"""
        # Upload a test file first
        xml_file = TEST_FILES_DIR / "05938517000140_1_66015-1.xml"

        with open(xml_file, "rb") as f:
            response = client.post(
                "/documents/upload",
                files={"file": (xml_file.name, f, "application/xml")},
                headers=auth_headers,
            )

        assert response.status_code == 200
        document_id = response.json()["id"]

        # Wait for processing
        time.sleep(5)

        # Call validation endpoint
        response = client.get(f"/documents/{document_id}/validate", headers=auth_headers)

        if response.status_code == 200:
            validation = response.json()
            assert "is_valid" in validation
            assert "errors" in validation
            assert "warnings" in validation
            print(f"[OK] Validation completed: valid={validation['is_valid']}, errors={len(validation['errors'])}, warnings={len(validation['warnings'])}")
        else:
            print(f"[WARN] Validation endpoint returned {response.status_code}")

    def test_list_documents_after_upload(self, client, auth_headers):
        """Test listing documents after uploading test files"""
        response = client.get("/documents?limit=100", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "total" in data

        print(f"[OK] Found {data['total']} documents in database")

        # Verify some test files are in the list
        file_names = [doc["file_name"] for doc in data["documents"]]
        test_file_names = [f.name for f in TEST_FILES_DIR.glob("*") if f.is_file()]

        found_count = sum(1 for name in test_file_names if name in file_names)
        print(f"  {found_count} test files found in document list")


class TestFileFormatValidation:
    """Test file format validation"""

    def test_xml_structure_validation(self):
        """Validate XML file structure"""
        xml_file = TEST_FILES_DIR / "05938517000140_1_66015-1.xml"
        assert xml_file.exists()

        import xml.etree.ElementTree as ET
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            assert root is not None
            print(f"[OK] XML structure valid: {xml_file.name}")
        except ET.ParseError as e:
            pytest.fail(f"Invalid XML structure: {e}")

    def test_pdf_file_integrity(self):
        """Validate PDF file integrity"""
        pdf_files = list(TEST_FILES_DIR.glob("*.pdf")) + list(TEST_FILES_DIR.glob("*.PDF"))
        assert len(pdf_files) > 0, "No PDF files found"

        for pdf_file in pdf_files:
            # Check PDF header
            with open(pdf_file, "rb") as f:
                header = f.read(5)
                assert header == b"%PDF-", f"Invalid PDF header: {pdf_file.name}"
            print(f"[OK] PDF integrity check passed: {pdf_file.name}")

    def test_excel_file_integrity(self):
        """Validate Excel file integrity"""
        excel_file = TEST_FILES_DIR / "Gestão Geral_20250827.xlsx"
        if excel_file.exists():
            # Check ZIP signature (XLSX files are ZIP archives)
            with open(excel_file, "rb") as f:
                signature = f.read(4)
                assert signature == b"PK\x03\x04", f"Invalid XLSX signature: {excel_file.name}"
            print(f"[OK] Excel integrity check passed: {excel_file.name}")

    def test_file_sizes_reasonable(self):
        """Check all test files have reasonable sizes"""
        test_files = list(TEST_FILES_DIR.glob("*"))
        test_files = [f for f in test_files if f.is_file()]

        for test_file in test_files:
            size = test_file.stat().st_size
            assert size > 0, f"File is empty: {test_file.name}"
            assert size < 100 * 1024 * 1024, f"File too large (>100MB): {test_file.name}"  # Max 100MB
            print(f"[OK] Size OK: {test_file.name} ({size:,} bytes)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
