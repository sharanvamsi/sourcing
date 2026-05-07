from cryptography.fernet import Fernet, InvalidToken
import os
import sentry_sdk
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# --- ENCRYPTION SETUP ---
# We use a MASTER_KEY from environment variables to encrypt/decrypt individual user keys.
MASTER_SECRET = os.getenv("MASTER_ENCRYPTION_SECRET")

# Old master secret for decrypting keys encrypted with a previous secret
# Set this when rotating MASTER_ENCRYPTION_SECRET to allow decryption of old keys
OLD_MASTER_SECRET = os.getenv("OLD_MASTER_ENCRYPTION_SECRET")

# Legacy fallback key for backward compatibility during migration
# This was the original hardcoded key used before environment variable was required
LEGACY_MASTER_SECRET = "club-safety-first-12345"

def _derive_key_from_secret(secret):
    """Derives a stable 32-byte Fernet key from a master secret."""
    if not secret:
        raise ValueError("Master secret cannot be None or empty")
    salt = b'aba-sourcing-salt' # High-quality salt recommended in production
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return key

def get_encryption_key():
    """Derives a stable 32-byte key from the master secret."""
    if not MASTER_SECRET:
        raise ValueError(
            "MASTER_ENCRYPTION_SECRET environment variable is not set. "
            "This is required for encryption. Please set it in your environment."
        )
    return _derive_key_from_secret(MASTER_SECRET)

def get_old_encryption_key():
    """Derives a key from the old master secret (for decrypting keys encrypted with previous secret)."""
    if not OLD_MASTER_SECRET:
        return None
    return _derive_key_from_secret(OLD_MASTER_SECRET)

def get_legacy_encryption_key():
    """Derives a key from the legacy hardcoded secret (for backward compatibility)."""
    return _derive_key_from_secret(LEGACY_MASTER_SECRET)

def encrypt_key(plain_text):
    """Encrypts a plain text string using the current master secret."""
    if not plain_text: return None
    if not MASTER_SECRET:
        error_msg = "Cannot encrypt: MASTER_ENCRYPTION_SECRET environment variable is not set"
        sentry_sdk.capture_message(error_msg, level="error")
        raise ValueError(error_msg)
    try:
        f = Fernet(get_encryption_key())
        return f.encrypt(plain_text.encode()).decode()
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return None

def decrypt_key(encrypted_text):
    """
    Decrypts an encrypted string, trying keys in this order:
    1. Current MASTER_ENCRYPTION_SECRET
    2. OLD_MASTER_ENCRYPTION_SECRET (if set, for keys encrypted with previous secret)
    3. Legacy hardcoded secret (for backward compatibility)
    
    This supports secret rotation without losing access to existing encrypted data.
    """
    if not encrypted_text: return None
    
    # First, try with the current master secret
    if MASTER_SECRET:
        try:
            f = Fernet(get_encryption_key())
            decrypted = f.decrypt(encrypted_text.encode()).decode()
            return decrypted
        except InvalidToken:
            # Current key failed, try old secret (if set)
            pass
        except Exception as e:
            # Other errors (not just wrong key) - log and continue to next attempt
            sentry_sdk.capture_exception(e)
    
    # Second, try with the old master secret (for keys encrypted before rotation)
    if OLD_MASTER_SECRET:
        try:
            f_old = Fernet(get_old_encryption_key())
            decrypted = f_old.decrypt(encrypted_text.encode()).decode()
            # Log that we used old key (for migration tracking)
            sentry_sdk.capture_message(
                "Decrypted API key using OLD_MASTER_ENCRYPTION_SECRET (re-encrypt with new secret recommended)",
                level="info"
            )
            return decrypted
        except InvalidToken:
            # Old key also failed, try legacy key
            pass
        except Exception as e:
            sentry_sdk.capture_exception(e)
    
    # Third, fallback to legacy key (for data encrypted with old hardcoded key)
    try:
        f_legacy = Fernet(get_legacy_encryption_key())
        decrypted = f_legacy.decrypt(encrypted_text.encode()).decode()
        # Log that we used legacy key (for migration tracking)
        sentry_sdk.capture_message(
            "Decrypted API key using legacy master secret (migration in progress)",
            level="info"
        )
        return decrypted
    except InvalidToken:
        # All keys failed - this is truly invalid data
        error_msg = "Failed to decrypt: Invalid token (current, old, and legacy keys all failed)"
        sentry_sdk.capture_message(error_msg, level="error")
        return None
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return None
