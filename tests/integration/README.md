# Integration Tests

These tests require a running server and are not part of the standard test suite.

## Running Integration Tests

Start the API server first:
```bash
uvicorn api:app --reload
```

Then run integration tests:
```bash
pytest tests/integration/ -v
```

## Files

- `test_api.py` - API endpoint integration tests
- `test_admin_access.py` - Admin access integration tests
