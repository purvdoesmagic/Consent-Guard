"""Argon2id password hashing and password policy."""

import re

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from flask import current_app

MIN_LENGTH = 12
MAX_LENGTH = 128

# Small deny-list of very common passwords (a production system would use a
# larger corpus such as a k-anonymity breached-password check).
COMMON_PASSWORDS = {
    "password1234", "passwordpassword", "123456789012", "qwertyuiopas", "letmein12345",
    "iloveyou1234", "administrator", "welcome12345", "changeme1234", "consentguard",
    "consentguard1", "password123!", "qwerty123456", "abc123456789",
}


def _hasher():
    cfg = current_app.config
    return PasswordHasher(
        time_cost=cfg["ARGON2_TIME_COST"],
        memory_cost=cfg["ARGON2_MEMORY_COST"],
        parallelism=cfg["ARGON2_PARALLELISM"],
        type=Type.ID,
    )


def hash_secret(secret: str) -> str:
    return _hasher().hash(secret)


def verify_secret(stored_hash: str, secret: str) -> bool:
    try:
        return _hasher().verify(stored_hash, secret)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


_dummy_hash = None


def dummy_verify(secret: str):
    """Spend comparable time when the account does not exist, to reduce
    username enumeration through response timing."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_secret("dummy-password-for-timing")
    verify_secret(_dummy_hash, secret)


def validate_password(password, username=None):
    """Return a list of policy violations (empty list = acceptable)."""
    problems = []
    if not isinstance(password, str):
        return ["Password must be a string."]
    if len(password) < MIN_LENGTH:
        problems.append(f"Password must be at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        problems.append(f"Password must be at most {MAX_LENGTH} characters.")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("Password is too common.")
    if username and username.lower() in password.lower():
        problems.append("Password must not contain the username.")
    if re.fullmatch(r"(.)\1*", password or ""):
        problems.append("Password must not be a single repeated character.")
    classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^A-Za-z0-9]"))
    if classes < 3:
        problems.append("Password must use at least three of: lowercase, uppercase, digits, symbols.")
    return problems
