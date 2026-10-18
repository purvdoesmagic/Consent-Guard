"""Encrypting personal data with AES-256-GCM.

The key comes from the .env file and is never stored in the database.
Each encryption uses a new random 12-byte nonce, which is saved
together with the encrypted text.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from flask import current_app


def check_key(key):
    """Stop the server from starting with a missing or wrong key."""
    if not key:
        raise RuntimeError("CG_ENCRYPTION_KEY is not set. Run: python scripts/setup_env.py")
    if len(base64.urlsafe_b64decode(key)) != 32:
        raise RuntimeError("CG_ENCRYPTION_KEY must be 32 bytes (base64 encoded).")


def _cipher():
    key = base64.urlsafe_b64decode(current_app.config["ENCRYPTION_KEY"])
    return AESGCM(key)


def encrypt(text):
    nonce = os.urandom(12)
    encrypted = _cipher().encrypt(nonce, text.encode("utf-8"), None)
    return base64.b64encode(nonce + encrypted).decode("ascii")


def decrypt(stored):
    raw = base64.b64decode(stored)
    nonce, encrypted = raw[:12], raw[12:]
    return _cipher().decrypt(nonce, encrypted, None).decode("utf-8")
