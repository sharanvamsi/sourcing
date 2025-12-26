from cryptography.fernet import Fernet
import os
import sentry_sdk
import base64
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# --- ENCRYPTION SETUP ---
# We use a MASTER_KEY from environment variables to encrypt/decrypt individual user keys.
# If no key is found, we generate one (though this would break decryption on reboot if not saved).
MASTER_SECRET = os.getenv("MASTER_ENCRYPTION_SECRET")

def get_encryption_key():
    """Derives a stable 32-byte key from the master secret."""
    salt = b'aba-sourcing-salt' # High-quality salt recommended in production
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(MASTER_SECRET.encode()))
    return key

def encrypt_key(plain_text):
    if not plain_text: return None
    try:
        f = Fernet(get_encryption_key())
        return f.encrypt(plain_text.encode()).decode()
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return None

def decrypt_key(encrypted_text):
    if not encrypted_text: return None
    try:
        f = Fernet(get_encryption_key())
        return f.decrypt(encrypted_text.encode()).decode()
    except Exception as e:
        sentry_sdk.capture_exception(e)
        return None # Decryption failed (wrong master key or corrupted data)
