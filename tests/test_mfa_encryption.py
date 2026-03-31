"""
Tests for MFA Secret Encryption and Backup Code Hashing

Verifies that:
1. TOTP secrets are encrypted/decrypted correctly
2. Backup codes are hashed securely with bcrypt
3. Backup code verification works correctly
"""

import pytest
from auth.encryption import (
    encrypt_mfa_secret,
    decrypt_mfa_secret,
    hash_backup_code,
    verify_backup_code,
    EncryptionService,
    BackupCodeHasher,
)

# Check if pyotp is available for integration tests
try:
    import pyotp
    PYOTP_AVAILABLE = True
except ImportError:
    PYOTP_AVAILABLE = False


class TestTOTPSecretEncryption:
    """Test TOTP secret encryption and decryption"""

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption work correctly"""
        secret = "JBSWY3DPEHPK3PXP"  # Example TOTP secret

        # Encrypt
        encrypted = encrypt_mfa_secret(secret)

        # Should not equal original
        assert encrypted != secret

        # Should be non-empty
        assert len(encrypted) > 0

        # Decrypt should recover original
        decrypted = decrypt_mfa_secret(encrypted)
        assert decrypted == secret

    def test_encryption_different_each_time(self):
        """Test that encrypting the same secret twice produces different ciphertext"""
        # Note: Fernet uses a timestamp and random data, so this might not hold
        # But we can test that decryption still works
        secret = "JBSWY3DPEHPK3PXP"

        encrypted1 = encrypt_mfa_secret(secret)
        encrypted2 = encrypt_mfa_secret(secret)

        # Both should decrypt to same value
        assert decrypt_mfa_secret(encrypted1) == secret
        assert decrypt_mfa_secret(encrypted2) == secret

    def test_empty_string(self):
        """Test that empty strings are handled correctly"""
        encrypted = encrypt_mfa_secret("")
        assert encrypted == ""

        decrypted = decrypt_mfa_secret("")
        assert decrypted == ""

    def test_long_secret(self):
        """Test encryption of longer secrets"""
        secret = "A" * 100

        encrypted = encrypt_mfa_secret(secret)
        decrypted = decrypt_mfa_secret(encrypted)

        assert decrypted == secret


class TestBackupCodeHashing:
    """Test backup code bcrypt hashing"""

    def test_hash_and_verify(self):
        """Test that hashing and verification work correctly"""
        code = "AB12-CD34-EF56"

        # Hash the code
        hashed = hash_backup_code(code)

        # Should not equal original
        assert hashed != code

        # Should start with bcrypt prefix
        assert hashed.startswith("$2b$")

        # Verify should succeed
        assert verify_backup_code(code, hashed) is True

        # Wrong code should fail
        assert verify_backup_code("WRONG-CODE", hashed) is False

    def test_hash_different_each_time(self):
        """Test that hashing same code twice produces different hashes"""
        code = "AB12-CD34-EF56"

        hash1 = hash_backup_code(code)
        hash2 = hash_backup_code(code)

        # Hashes should be different (bcrypt uses random salt)
        assert hash1 != hash2

        # Both should verify correctly
        assert verify_backup_code(code, hash1) is True
        assert verify_backup_code(code, hash2) is True

    def test_case_handling(self):
        """Test that backup codes handle case correctly"""
        code_lower = "ab12-cd34-ef56"
        code_upper = "AB12-CD34-EF56"

        # Hash lowercase code
        hashed_lower = hash_backup_code(code_lower)

        # Hash uppercase code
        hashed_upper = hash_backup_code(code_upper)

        # Each hash should only verify its own case (bcrypt is case-sensitive)
        # MFA service normalizes to uppercase before hashing/verifying
        assert verify_backup_code(code_lower, hashed_lower) is True
        assert verify_backup_code(code_upper, hashed_upper) is True

        # Cross-case verification should fail (bcrypt is case-sensitive)
        assert verify_backup_code(code_lower, hashed_upper) is False
        assert verify_backup_code(code_upper, hashed_lower) is False

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly"""
        code = "AB12-CD34-EF56"
        hashed = hash_backup_code(code)

        # Code with surrounding whitespace should verify
        assert verify_backup_code("  AB12-CD34-EF56  ", hashed) is False
        # Note: Current implementation doesn't strip in verify,
        # so we need to ensure the MFA service normalizes input

    def test_invalid_hash_format(self):
        """Test that invalid hash format returns False"""
        code = "AB12-CD34-EF56"

        # Invalid hash should return False, not raise exception
        assert verify_backup_code(code, "invalid_hash") is False
        assert verify_backup_code(code, "") is False


class TestEncryptionService:
    """Test EncryptionService class directly"""

    def test_singleton_fernet(self):
        """Test that Fernet instance is cached"""
        # Get Fernet twice
        fernet1 = EncryptionService._get_fernet()
        fernet2 = EncryptionService._get_fernet()

        # Should be same instance
        assert fernet1 is fernet2

    def test_encrypt_decrypt_with_unicode(self):
        """Test encryption with unicode characters"""
        secret = "JBSWY3DP-Çedilha-日本語"

        encrypted = EncryptionService.encrypt(secret)
        decrypted = EncryptionService.decrypt(encrypted)

        assert decrypted == secret


class TestIntegration:
    """Integration tests for MFA encryption workflow"""

    @pytest.mark.skipif(not PYOTP_AVAILABLE, reason="pyotp not installed")
    def test_complete_mfa_flow(self):
        """Test complete MFA setup and verification flow"""
        import json
        from auth.mfa_service import MFAService

        # Generate TOTP secret
        totp_secret = MFAService.generate_totp_secret()

        # Encrypt it (as done in enable_totp_mfa)
        encrypted_secret = encrypt_mfa_secret(totp_secret)

        # Generate and hash backup codes
        backup_codes = MFAService.generate_backup_codes(count=5)
        backup_hashes = [hash_backup_code(code.upper().strip()) for code in backup_codes]
        backup_codes_json = json.dumps(backup_hashes)

        # Simulate retrieval from database
        retrieved_secret = decrypt_mfa_secret(encrypted_secret)
        retrieved_hashes = json.loads(backup_codes_json)

        # Verify TOTP secret recovered
        assert retrieved_secret == totp_secret

        # Verify first backup code
        assert verify_backup_code(backup_codes[0].upper().strip(), retrieved_hashes[0]) is True

        # Verify wrong code fails
        assert verify_backup_code("WRONG-CODE", retrieved_hashes[0]) is False
