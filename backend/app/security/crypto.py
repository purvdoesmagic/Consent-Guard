"""AES-256-GCM encryption for protected records and MFA secrets.

Design:
* The 256-bit key is loaded from the ``CG_ENCRYPTION_KEY`` environment
  variable (URL-safe base64). It is never stored in the database.
* Every encryption uses a fresh 96-bit nonce from ``os.urandom`` (a CSPRNG).
  With random 96-bit nonces, NIST SP 800-38D advises staying below 2**32
  encryptions per key; this local demo is many orders of magnitude below that.
* Associated data (AAD) binds each ciphertext to its context (purpose, record
  id, owner, category). Moving a ciphertext to a different record, or using
  an MFA ciphertext as a record, fails authentication.
* Any key, nonce, ciphertext or AAD tampering raises ``DecryptionError``;
  plaintext is never returned on failure.
"""

import base64
import binascii
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32


class KeyConfigurationError(RuntimeError):
    """Raised when the encryption key is missing or malformed."""


class DecryptionError(Exception):
    """Raised when a ciphertext cannot be authenticated/decrypted."""


def generate_key_b64():
    return base64.urlsafe_b64encode(os.urandom(KEY_BYTES)).decode("ascii")


def parse_key(value):
    if not value or not isinstance(value, str):
        raise KeyConfigurationError(
            "CG_ENCRYPTION_KEY is not set. Run 'python scripts/setup_env.py' to create a development key."
        )
    if value.startswith("REPLACE_WITH"):
        raise KeyConfigurationError("CG_ENCRYPTION_KEY still contains the .env.example placeholder.")
    try:
        raw = base64.urlsafe_b64decode(value.strip().encode("ascii"))
    except (binascii.Error, ValueError, UnicodeEncodeError):
        raise KeyConfigurationError("CG_ENCRYPTION_KEY is not valid URL-safe base64.")
    if len(raw) != KEY_BYTES:
        raise KeyConfigurationError(
            f"CG_ENCRYPTION_KEY must decode to {KEY_BYTES} bytes (got {len(raw)})."
        )
    return raw


def _aad_bytes(aad):
    return json.dumps(aad, sort_keys=True, separators=(",", ":")).encode("utf-8")


class Cipher:
    def __init__(self, key_b64, key_id):
        self._aesgcm = AESGCM(parse_key(key_b64))
        if not key_id or not isinstance(key_id, str) or len(key_id) > 32:
            raise KeyConfigurationError("CG_ENCRYPTION_KEY_ID must be a short non-empty string.")
        self.key_id = key_id

    def encrypt(self, plaintext: bytes, aad: dict):
        nonce = os.urandom(NONCE_BYTES)
        ct = self._aesgcm.encrypt(nonce, plaintext, _aad_bytes(aad))
        return {
            "key_id": self.key_id,
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(ct).decode("ascii"),
        }

    def decrypt(self, key_id, nonce_b64, ciphertext_b64, aad: dict) -> bytes:
        if key_id != self.key_id:
            raise DecryptionError("Ciphertext was produced with a different key id.")
        try:
            nonce = base64.b64decode(nonce_b64, validate=True)
            ct = base64.b64decode(ciphertext_b64, validate=True)
            if len(nonce) != NONCE_BYTES:
                raise DecryptionError("Invalid nonce length.")
            return self._aesgcm.decrypt(nonce, ct, _aad_bytes(aad))
        except (InvalidTag, binascii.Error, ValueError):
            raise DecryptionError("Ciphertext failed authentication.")

    # Compact single-string form used for small secrets (MFA seeds).
    def encrypt_str(self, text: str, aad: dict) -> str:
        box = self.encrypt(text.encode("utf-8"), aad)
        return f"{box['key_id']}:{box['nonce']}:{box['ciphertext']}"

    def decrypt_str(self, packed: str, aad: dict) -> str:
        try:
            key_id, nonce, ct = packed.split(":", 2)
        except (AttributeError, ValueError):
            raise DecryptionError("Malformed encrypted value.")
        return self.decrypt(key_id, nonce, ct, aad).decode("utf-8")


def get_cipher():
    from flask import current_app

    return current_app.extensions["cg_cipher"]
