"""Authentication, MFA and account-security endpoints."""

from flask import Blueprint, current_app, g, request
from sqlalchemy.exc import IntegrityError

from app.constants import SELF_REGISTER_ROLES
from app.extensions import db, limiter
from app.models import RecoveryCode, User, UserSession
from app.security import mfa
from app.security.crypto import DecryptionError
from app.security.passwords import dummy_verify, hash_secret, validate_password, verify_secret
from app.security.sessions import (
    clear_cookie_on_response, create_session, login_required, pending_mfa_required, revoke_session,
)
from app.services import audit
from app.services.users import UserCreationError, create_user, normalize_username, username_fingerprint
from app.utils.errors import ApiError
from app.utils.time import to_iso, utcnow
from app.utils.validation import get_choice, get_str, invalid, json_body

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

INVALID_LOGIN = "Invalid username or password."


def _login_limit():
    return current_app.config["LOGIN_RATE_LIMIT"]


def _mfa_limit():
    return current_app.config["MFA_RATE_LIMIT"]


def _register_limit():
    return current_app.config["REGISTER_RATE_LIMIT"]


def _username_key():
    data = request.get_json(silent=True) or {}
    return "login-user:" + username_fingerprint(str(data.get("username", "")))


def _pending_user_key():
    return f"mfa-user:{g.user.id if g.get('user') else request.remote_addr}"


def _session_payload():
    if g.user is None:
        return {"authenticated": False, "mfa_pending": False, "user": None, "csrf_token": None}
    return {
        "authenticated": not g.session.mfa_pending,
        "mfa_pending": g.session.mfa_pending,
        "user": g.user.to_self() if not g.session.mfa_pending else None,
        "csrf_token": g.session.csrf_token,
        "session_expires_at": to_iso(g.session.expires_at),
    }


@bp.get("/session")
def session_info():
    return _session_payload()


@bp.post("/register")
@limiter.limit(_register_limit)
def register():
    data = json_body()
    role = get_choice(data, "role", SELF_REGISTER_ROLES, required=False) or "subject"
    try:
        user = create_user(
            get_str(data, "username", max_len=32),
            get_str(data, "password", max_len=256, strip=False),
            get_str(data, "display_name", max_len=80),
            role,
        )
    except UserCreationError as err:
        raise invalid(err.field, str(err))
    except IntegrityError:
        db.session.rollback()
        raise invalid("username", "That username is not available.")
    return {"user": user.to_public()}, 201


@bp.post("/login")
@limiter.limit(_login_limit)
@limiter.limit(_login_limit, key_func=_username_key)
def login():
    data = json_body()
    username = normalize_username(get_str(data, "username", max_len=64))
    password = get_str(data, "password", max_len=256, strip=False)
    user = User.query.filter_by(username=username).first()

    if user is None or not user.is_active:
        dummy_verify(password)
        ok = False
    else:
        ok = verify_secret(user.password_hash, password)

    if not ok:
        audit.record("auth.login.failure", "failure", subject_id=user.id if user else None,
                     resource_type="user", resource_id=user.id if user else None, action="login",
                     reason_code="INVALID_CREDENTIALS" if user else "UNKNOWN_ACCOUNT",
                     details={"username_fp": username_fingerprint(username)})
        raise ApiError(401, "INVALID_CREDENTIALS", INVALID_LOGIN)

    revoke_session(g.session)  # never reuse a pre-login session (fixation defence)
    if user.mfa_enabled:
        create_session(user, mfa_pending=True)
        audit.stage("auth.login.password_verified", "success", actor_id=user.id, subject_id=user.id,
                    resource_type="user", resource_id=user.id, action="login", reason_code="MFA_CHALLENGE")
        audit.commit()
        return {"mfa_required": True, "csrf_token": g.session.csrf_token}

    create_session(user)
    audit.stage("auth.login.success", "success", actor_id=user.id, subject_id=user.id,
                resource_type="user", resource_id=user.id, action="login", details={"mfa": False})
    audit.commit()
    return {"mfa_required": False, **_session_payload()}


@bp.post("/mfa/verify")
@limiter.limit(_mfa_limit)
@limiter.limit(_mfa_limit, key_func=_pending_user_key)
@pending_mfa_required
def mfa_verify():
    data = json_body()
    user = g.user
    code = get_str(data, "code", required=False, max_len=6)
    recovery = get_str(data, "recovery_code", required=False, max_len=20)
    method = None
    if code:
        try:
            secret = mfa.decrypt_secret(user.id, user.mfa_secret_enc)
        except DecryptionError:
            current_app.logger.error("MFA secret for user %s could not be decrypted", user.id)
            raise ApiError(500, "MFA_UNAVAILABLE", "MFA verification is unavailable. Contact an administrator.")
        step = mfa.match_totp(secret, code, user.mfa_last_timestep)
        if step is not None:
            user.mfa_last_timestep = step
            method = "totp"
    elif recovery and mfa.consume_recovery_code(user, recovery):
        method = "recovery_code"

    if method is None:
        audit.record("auth.mfa.failure", "failure", actor_id=user.id, subject_id=user.id, resource_type="user",
                     resource_id=user.id, action="mfa_verify", reason_code="INVALID_MFA_CODE")
        raise ApiError(401, "INVALID_MFA_CODE", "The verification code is invalid or has already been used.")

    revoke_session(g.session)
    create_session(user, mfa_verified=True)  # rotate token after the second factor
    details = {"method": method}
    if method == "recovery_code":
        details["recovery_codes_remaining"] = sum(1 for c in user.recovery_codes if c.used_at is None)
    audit.stage("auth.login.success", "success", actor_id=user.id, subject_id=user.id, resource_type="user",
                resource_id=user.id, action="login", details={"mfa": True, **details})
    audit.commit()
    return _session_payload()


@bp.post("/logout")
def logout():
    if g.session is not None:
        revoke_session(g.session)
        audit.record("auth.logout", "success", actor_id=g.user.id, subject_id=g.user.id,
                     resource_type="session", resource_id=g.session.id, action="logout")
    clear_cookie_on_response()
    return {"ok": True}


@bp.get("/me")
@login_required
def me():
    return {"user": g.user.to_self()}


@bp.post("/mfa/setup")
@login_required
def mfa_setup():
    user = g.user
    if user.mfa_enabled:
        raise ApiError(409, "MFA_ALREADY_ENABLED", "MFA is already enabled. Disable it first to re-enroll.")
    secret = mfa.new_secret()
    user.mfa_pending_secret_enc = mfa.encrypt_secret(user.id, secret, kind="pending")
    db.session.commit()
    uri, qr = mfa.provisioning(user, secret)
    # The secret is returned once so it can be typed into an authenticator app
    # when the QR code cannot be scanned. It is stored only in encrypted form.
    return {"secret": secret, "otpauth_uri": uri, "qr_svg_data_uri": qr}


@bp.post("/mfa/enable")
@login_required
def mfa_enable():
    user = g.user
    data = json_body()
    code = get_str(data, "code", max_len=6)
    if user.mfa_enabled:
        raise ApiError(409, "MFA_ALREADY_ENABLED", "MFA is already enabled.")
    if not user.mfa_pending_secret_enc:
        raise ApiError(409, "MFA_SETUP_REQUIRED", "Start MFA setup first.")
    secret = mfa.decrypt_secret(user.id, user.mfa_pending_secret_enc, kind="pending")
    step = mfa.match_totp(secret, code, None)
    if step is None:
        audit.record("auth.mfa.enroll_failure", "failure", actor_id=user.id, subject_id=user.id,
                     resource_type="user", resource_id=user.id, action="mfa_enable", reason_code="INVALID_MFA_CODE")
        raise ApiError(400, "INVALID_MFA_CODE", "The code did not match. Check your device clock and try again.")
    user.mfa_secret_enc = mfa.encrypt_secret(user.id, secret)
    user.mfa_pending_secret_enc = None
    user.mfa_enabled = True
    user.mfa_last_timestep = step
    codes = mfa.issue_recovery_codes(user)
    g.session.mfa_verified = True
    # Other sessions were created without MFA; revoke them.
    for other in UserSession.query.filter(UserSession.user_id == user.id, UserSession.id != g.session.id,
                                          UserSession.revoked_at.is_(None)).all():
        revoke_session(other)
    audit.stage("auth.mfa.enabled", "success", actor_id=user.id, subject_id=user.id, resource_type="user",
                resource_id=user.id, action="mfa_enable")
    audit.commit()
    return {"user": user.to_self(), "recovery_codes": codes}


def _reauthenticate(data, require_code=True):
    user = g.user
    password = get_str(data, "password", max_len=256, strip=False)
    if not verify_secret(user.password_hash, password):
        audit.record("auth.reauth.failure", "failure", actor_id=user.id, subject_id=user.id,
                     resource_type="user", resource_id=user.id, action="reauthenticate",
                     reason_code="INVALID_CREDENTIALS")
        raise ApiError(401, "INVALID_CREDENTIALS", "Current password is incorrect.")
    if require_code and user.mfa_enabled:
        code = get_str(data, "code", max_len=6)
        step = mfa.match_totp(mfa.decrypt_secret(user.id, user.mfa_secret_enc), code, user.mfa_last_timestep)
        if step is None:
            audit.record("auth.mfa.failure", "failure", actor_id=user.id, subject_id=user.id, resource_type="user",
                         resource_id=user.id, action="reauthenticate", reason_code="INVALID_MFA_CODE")
            raise ApiError(401, "INVALID_MFA_CODE", "The verification code is invalid or has already been used.")
        user.mfa_last_timestep = step


@bp.post("/mfa/disable")
@login_required
def mfa_disable():
    user = g.user
    if not user.mfa_enabled:
        raise ApiError(409, "MFA_NOT_ENABLED", "MFA is not enabled.")
    _reauthenticate(json_body())
    user.mfa_enabled = False
    user.mfa_secret_enc = None
    user.mfa_last_timestep = None
    RecoveryCode.query.filter_by(user_id=user.id).delete()
    g.session.mfa_verified = False
    audit.stage("auth.mfa.disabled", "success", actor_id=user.id, subject_id=user.id, resource_type="user",
                resource_id=user.id, action="mfa_disable")
    audit.commit()
    return {"user": user.to_self()}


@bp.post("/mfa/recovery-codes")
@login_required
def regenerate_recovery_codes():
    user = g.user
    if not user.mfa_enabled:
        raise ApiError(409, "MFA_NOT_ENABLED", "Enable MFA first.")
    _reauthenticate(json_body())
    codes = mfa.issue_recovery_codes(user)
    audit.stage("auth.recovery_codes.regenerated", "success", actor_id=user.id, subject_id=user.id,
                resource_type="user", resource_id=user.id, action="regenerate")
    audit.commit()
    return {"recovery_codes": codes}


@bp.post("/password")
@login_required
def change_password():
    user = g.user
    data = json_body()
    _reauthenticate({"password": data.get("current_password")}, require_code=False)
    new_password = get_str(data, "new_password", max_len=256, strip=False)
    problems = validate_password(new_password, user.username)
    if problems:
        raise invalid("new_password", " ".join(problems))
    user.password_hash = hash_secret(new_password)
    revoked = 0
    for other in UserSession.query.filter(UserSession.user_id == user.id, UserSession.id != g.session.id,
                                          UserSession.revoked_at.is_(None)).all():
        revoke_session(other)
        revoked += 1
    audit.stage("auth.password.changed", "success", actor_id=user.id, subject_id=user.id, resource_type="user",
                resource_id=user.id, action="update", details={"sessions_revoked": revoked})
    audit.commit()
    return {"ok": True, "sessions_revoked": revoked}


@bp.get("/sessions")
@login_required
def list_sessions():
    now = utcnow()
    sessions = (
        UserSession.query.filter(UserSession.user_id == g.user.id, UserSession.revoked_at.is_(None),
                                 UserSession.expires_at > now, UserSession.mfa_pending.is_(False))
        .order_by(UserSession.created_at.desc()).all()
    )
    return {"sessions": [s.to_dict(current_id=g.session.id) for s in sessions]}


@bp.post("/sessions/revoke-others")
@login_required
def revoke_other_sessions():
    revoked = 0
    for other in UserSession.query.filter(UserSession.user_id == g.user.id, UserSession.id != g.session.id,
                                          UserSession.revoked_at.is_(None)).all():
        revoke_session(other)
        revoked += 1
    audit.record("auth.session.revoked", "success", actor_id=g.user.id, subject_id=g.user.id,
                 resource_type="session", action="revoke_others", details={"sessions_revoked": revoked})
    return {"sessions_revoked": revoked}
