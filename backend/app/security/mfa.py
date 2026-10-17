"""TOTP multi-factor authentication (RFC 6238) and single-use recovery codes."""

import hmac
import re
import secrets
from datetime import timezone

import pyotp
import segno

from app.extensions import db
from app.models import RecoveryCode
from app.security.crypto import get_cipher
from app.security.passwords import hash_secret, verify_secret
from app.utils.time import utcnow

ISSUER = "ConsentGuard"
RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I ambiguity


def _aad(user_id, kind):
    return {"purpose": "mfa-secret", "user_id": user_id, "kind": kind}


def encrypt_secret(user_id, secret, kind="active"):
    return get_cipher().encrypt_str(secret, _aad(user_id, kind))


def decrypt_secret(user_id, packed, kind="active"):
    return get_cipher().decrypt_str(packed, _aad(user_id, kind))


def new_secret():
    return pyotp.random_base32()  # 160-bit secret


def provisioning(user, secret):
    uri = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name=ISSUER)
    svg = segno.make(uri, error="m").svg_data_uri(scale=5, border=2)
    return uri, svg


def match_totp(secret, code, last_timestep, at=None):
    """Return the matched time-step if ``code`` is valid and not replayed.

    Accepts the current 30 s step and one step either side for clock drift.
    A step at or before ``last_timestep`` is rejected (replay protection).
    """
    if not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
        return None
    totp = pyotp.TOTP(secret)
    now = (at or utcnow()).replace(tzinfo=timezone.utc)
    current = int(now.timestamp() // totp.interval)
    for step in (current - 1, current, current + 1):
        if hmac.compare_digest(totp.generate_otp(step), code):
            if last_timestep is not None and step <= last_timestep:
                return None
            return step
    return None


def _format_code(raw):
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def normalize_recovery_code(code):
    return re.sub(r"[\s-]", "", code or "").upper()


def issue_recovery_codes(user):
    """Replace all recovery codes; returns plaintext codes (shown once)."""
    RecoveryCode.query.filter_by(user_id=user.id).delete()
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        codes.append(_format_code(raw))
        db.session.add(RecoveryCode(user_id=user.id, code_hash=hash_secret(raw)))
    return codes


def consume_recovery_code(user, code):
    """Mark a matching unused recovery code as used. Returns True on success."""
    normalized = normalize_recovery_code(code)
    if not re.fullmatch(r"[A-Z0-9]{10}", normalized):
        return False
    for rc in RecoveryCode.query.filter_by(user_id=user.id, used_at=None).all():
        if verify_secret(rc.code_hash, normalized):
            rc.used_at = utcnow()
            return True
    return False
