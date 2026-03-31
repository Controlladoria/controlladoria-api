"""
Test script for the API
Tests the complete flow: upload → AI → JSON → DB
"""

import json
from pathlib import Path

import requests

# API base URL
BASE_URL = "http://localhost:8000"


def test_health():
    """Test API health check"""
    print("Testing API health check...")
    response = requests.get(f"{BASE_URL}/")
    print(f"✓ Status: {response.status_code}")
    print(f"  Response: {response.json()}\n")


def test_upload(file_path: str):
    """Test document upload"""
    print(f"Testing document upload: {file_path}")

    if not Path(file_path).exists():
        print(f"✗ File not found: {file_path}\n")
        return None

    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f)}
        response = requests.post(f"{BASE_URL}/documents/upload", files=files)

    print(f"✓ Status: {response.status_code}")
    result = response.json()
    print(f"  Document ID: {result['id']}")
    print(f"  Status: {result['status']}")
    print(f"  Message: {result['message']}\n")

    return result["id"]


def test_get_document(doc_id: int):
    """Test getting document details"""
    print(f"Testing get document details (ID: {doc_id})...")

    response = requests.get(f"{BASE_URL}/documents/{doc_id}")

    print(f"✓ Status: {response.status_code}")
    result = response.json()

    print(f"  File: {result['file_name']}")
    print(f"  Status: {result['status']}")
    print(f"  Upload Date: {result['upload_date']}")

    if result.get("extracted_data"):
        print(f"\n  Extracted Data:")
        print(f"    Document Type: {result['extracted_data'].get('document_type')}")
        print(
            f"    Transaction Type: {result['extracted_data'].get('transaction_type')}"
        )
        print(
            f"    Total Amount: {result['extracted_data'].get('total_amount')} {result['extracted_data'].get('currency')}"
        )

        if result["extracted_data"].get("issuer"):
            print(f"    Issuer: {result['extracted_data']['issuer'].get('name')}")

        print(f"\n  Full JSON:")
        print(json.dumps(result["extracted_data"], indent=2))

    print()
    return result


def test_list_documents():
    """Test listing all documents"""
    print("Testing list documents...")

    response = requests.get(f"{BASE_URL}/documents")

    print(f"✓ Status: {response.status_code}")
    result = response.json()

    print(f"  Total documents: {result['total']}")
    print(f"  Documents in response: {len(result['documents'])}")

    for doc in result["documents"][:5]:  # Show first 5
        print(f"    - ID {doc['id']}: {doc['file_name']} ({doc['status']})")

    print()


def test_stats():
    """Test stats endpoint"""
    print("Testing stats endpoint...")

    response = requests.get(f"{BASE_URL}/stats")

    print(f"✓ Status: {response.status_code}")
    result = response.json()

    print(f"  Total Documents: {result['total_documents']}")
    print(f"  Completed: {result['completed']}")
    print(f"  Failed: {result['failed']}")
    print(f"  Pending: {result['pending']}")
    print(f"  Processing: {result['processing']}")
    print()


def run_tests():
    """Run all tests"""
    print("=" * 60)
    print("DreSystem API Tests - Week 2")
    print("=" * 60)
    print()

    # Test 1: Health check
    try:
        test_health()
    except Exception as e:
        print(f"✗ Health check failed: {e}")
        print("\nMake sure the API is running:")
        print("  python api.py")
        return

    # Test 2: Stats (before upload)
    try:
        test_stats()
    except Exception as e:
        print(f"✗ Stats test failed: {e}\n")

    # Test 3: Upload a document
    test_file = input(
        "Enter path to test document (or press Enter to skip upload test): "
    ).strip()

    doc_id = None
    if test_file:
        try:
            doc_id = test_upload(test_file)
        except Exception as e:
            print(f"✗ Upload failed: {e}\n")

    # Test 4: Get document details
    if doc_id:
        try:
            test_get_document(doc_id)
        except Exception as e:
            print(f"✗ Get document failed: {e}\n")

    # Test 5: List documents
    try:
        test_list_documents()
    except Exception as e:
        print(f"✗ List documents failed: {e}\n")

    # Test 6: Stats (after upload)
    try:
        test_stats()
    except Exception as e:
        print(f"✗ Stats test failed: {e}\n")

    print("=" * 60)
    print("Tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
