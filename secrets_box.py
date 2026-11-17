"""secrets_box.py — encrypts small secrets (Git tokens, environment variables) before they
are stored in the database. Key = TOKEN_KEY if set, otherwise the app's SECRET_KEY.
Losing or changing the key makes stored secrets unreadable, so keep it stable."""
import os
import base64
import hashlib

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:          # requirements.txt lists cryptography
    Fernet = None
    InvalidToken = Exception

_secret_key = ""


class SecretsError(Exception):
    pass


def configure(secret_key):
    global _secret_key
    _secret_key = str(secret_key or "")


def _fernet():
    if Fernet is None:
        raise SecretsError("Encryption is unavailable on this server (cryptography is not installed).")
    key = (os.environ.get("TOKEN_KEY") or "").strip() or _secret_key
    if not key:
        raise SecretsError("No SECRET_KEY configured, so secrets cannot be stored safely.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def encrypt(text):
    return _fernet().encrypt(text.encode()).decode()


def decrypt(blob):
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken:
        return None
