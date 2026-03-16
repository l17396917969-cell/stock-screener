import os
from cryptography.fernet import Fernet
import base64

def get_cipher():
    # Use APP_SECRET_KEY as base for Fernet key if KEYSTORE_MASTER_KEY is not set
    # Fernet key must be 32 url-safe base64-encoded bytes
    key = os.environ.get('KEYSTORE_MASTER_KEY')
    if not key:
        # Fallback: deriving a key from SECRET_KEY (deterministic but less secure than a random one)
        # For production, KEYSTORE_MASTER_KEY should be set in .env
        secret = os.environ.get('SECRET_KEY', 'default-secret-key-for-stock-screener-123')
        # Simple padding/truncation to get 32 bytes
        key_bytes = (secret * 4)[:32].encode()
        key = base64.urlsafe_b64encode(key_bytes).decode()
    
    return Fernet(key)

def encrypt_key(plain_text):
    if not plain_text:
        return None
    cipher = get_cipher()
    return cipher.encrypt(plain_text.encode()).decode()

def decrypt_key(encrypted_text):
    if not encrypted_text:
        return None
    cipher = get_cipher()
    try:
        return cipher.decrypt(encrypted_text.encode()).decode()
    except Exception:
        return None
