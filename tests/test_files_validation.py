"""
Standalone file validation tests for test_files folder
No API server or fixtures required
"""

import os
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

# Test files directory
TEST_FILES_DIR = Path(__file__).parent.parent / "test_files"


def test_test_files_directory_exists():
    """Verify test_files directory exists"""
    assert TEST_FILES_DIR.exists(), f"test_files directory not found at {TEST_FILES_DIR}"
    assert TEST_FILES_DIR.is_dir(), "test_files is not a directory"
    print(f"[OK] test_files directory exists: {TEST_FILES_DIR}")


def test_xml_structure_validation():
    """Validate XML file structure"""
    xml_files = list(TEST_FILES_DIR.glob("*.xml"))
    assert len(xml_files) > 0, "No XML files found"

    for xml_file in xml_files:
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            assert root is not None
            print(f"[OK] XML structure valid: {xml_file.name}")
        except ET.ParseError as e:
            print(f"[FAIL] Invalid XML structure in {xml_file.name}: {e}")
            raise


def test_pdf_file_integrity():
    """Validate PDF file integrity"""
    pdf_files = list(TEST_FILES_DIR.glob("*.pdf")) + list(TEST_FILES_DIR.glob("*.PDF"))
    assert len(pdf_files) > 0, "No PDF files found"

    for pdf_file in pdf_files:
        # Check PDF header
        with open(pdf_file, "rb") as f:
            header = f.read(5)
            assert header == b"%PDF-", f"Invalid PDF header: {pdf_file.name}"
        print(f"[OK] PDF integrity check passed: {pdf_file.name}")


def test_excel_file_integrity():
    """Validate Excel file integrity"""
    excel_files = list(TEST_FILES_DIR.glob("*.xlsx"))

    if len(excel_files) == 0:
        print("[WARN] No Excel files found")
        return

    for excel_file in excel_files:
        # Check ZIP signature (XLSX files are ZIP archives)
        with open(excel_file, "rb") as f:
            signature = f.read(4)
            assert signature == b"PK\x03\x04", f"Invalid XLSX signature: {excel_file.name}"
        print(f"[OK] Excel integrity check passed: {excel_file.name}")


def test_file_sizes_reasonable():
    """Check all test files have reasonable sizes"""
    test_files = list(TEST_FILES_DIR.glob("*"))
    test_files = [f for f in test_files if f.is_file()]

    assert len(test_files) > 0, "No files found in test_files directory"

    for test_file in test_files:
        size = test_file.stat().st_size
        assert size > 0, f"File is empty: {test_file.name}"
        assert size < 100 * 1024 * 1024, f"File too large (>100MB): {test_file.name}"
        print(f"[OK] Size check passed: {test_file.name} ({size:,} bytes)")


def test_list_all_files():
    """List all files in test_files directory"""
    test_files = list(TEST_FILES_DIR.glob("*"))
    test_files = [f for f in test_files if f.is_file()]

    print(f"\n[INFO] Found {len(test_files)} files in test_files directory:")
    for test_file in test_files:
        size = test_file.stat().st_size
        print(f"  - {test_file.name} ({size:,} bytes, {test_file.suffix})")


def test_file_type_distribution():
    """Show distribution of file types"""
    test_files = list(TEST_FILES_DIR.glob("*"))
    test_files = [f for f in test_files if f.is_file()]

    file_types = {}
    for test_file in test_files:
        ext = test_file.suffix.lower()
        file_types[ext] = file_types.get(ext, 0) + 1

    print(f"\n[INFO] File type distribution:")
    for ext, count in sorted(file_types.items()):
        print(f"  {ext}: {count} file(s)")


if __name__ == "__main__":
    print("=" * 70)
    print("TEST FILES VALIDATION")
    print("=" * 70)

    tests = [
        test_test_files_directory_exists,
        test_list_all_files,
        test_file_type_distribution,
        test_xml_structure_validation,
        test_pdf_file_integrity,
        test_excel_file_integrity,
        test_file_sizes_reasonable,
    ]

    passed = 0
    failed = 0

    for test in tests:
        test_name = test.__name__.replace("_", " ").title()
        print(f"\n{test_name}:")
        print("-" * 70)
        try:
            test()
            passed += 1
            print(f"[PASS] {test_name}")
        except Exception as e:
            failed += 1
            print(f"[FAIL] {test_name}: {e}")

    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    sys.exit(0 if failed == 0 else 1)
