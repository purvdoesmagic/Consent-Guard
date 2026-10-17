"""Server-managed sessions, CSRF protection and access decorators.

* The session cookie carries a 256-bit random token. The database stores only
  its SHA-256 digest, so a database leak does not reveal usable cookies.
* Cookies are HttpOnly, SameSite=Strict, Path=/ and Secure when configured.
* Sessions expire after an idle timeout and an absolute lifetime, and can be
  revoked (logout, password change, "sign out other sessions").
* A fresh token is issued at login and again after MFA verification, which
  prevents session fixation.
* Every state-changing request that carries a session must send the
  per-session CSRF token in the ``X-CSRF-Token`` header (synchronizer token
  pattern). Requests whose ``Origin`` is not in the allow-list are rejected.
"""

import hashlib
import hmac
import secrets
from datetime import timedelta
from functools import wraps

from flask import current_app, g, request

from app.extensions import db
from app.models import UserSession
from app.services import audit
from app.utils.errors import ApiError
from app.utils.time import utcnow

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LAST_SEEN_RESOLUTION = timedelta(seconds=60)


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(user, *, mfa_pending=False, mfa_verified=False):
    cfg = current_app.config
    token = secrets.token_urlsafe(32)
    now = utcnow()
    lifetime = (
        timedelta(minutes=cfg["PENDING_MFA_MINUTES"]) if mfa_pending else timedelta(hours=cfg["SESSION_ABSOLUTE_HOURS"])
    )
    session = UserSession(
        token_hash=hash_token(token),
        user_id=user.id,
        csrf_token=secrets.token_urlsafe(32),
        mfa_pending=mfa_pending,
        mfa_verified=mfa_verified,
        created_at=now,
        last_seen_at=now,
        expires_at=now + lifetime,
        user_agent=(request.headers.get("User-Agent") or "")[:200],
    )
    db.session.add(session)
    g.new_session_token = token
    g.session = session
    g.user = user
    return session


def revoke_session(session):
    if session is not None and session.revoked_at is None:
        session.revoked_at = utcnow()


def clear_cookie_on_response():
    g.clear_session_cookie = True


def _session_rejection(session, now):
    cfg = current_app.config
    if session is None:
        return "SESSION_UNKNOWN"
    if session.revoked_at is not None:
        return "SESSION_REVOKED"
    if now >= session.expires_at:
        return "SESSION_EXPIRED"
    if not session.mfa_pending and now - session.last_seen_at > timedelta(minutes=cfg["SESSION_IDLE_MINUTES"]):
        return "SESSION_IDLE_TIMEOUT"
    if not session.user.is_active:
        return "ACCOUNT_DISABLED"
    return None


def load_session():
    """before_request hook: resolve the session cookie into g.session/g.user."""
    g.session = None
    g.user = None
    g.session_rejection = None
    token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    if not token or len(token) > 128:
        return
    session = UserSession.query.filter_by(token_hash=hash_token(token)).first()
    now = utcnow()
    reason = _session_rejection(session, now)
    if reason:
        g.session_rejection = reason
        clear_cookie_on_response()
        if session is not None and reason != "SESSION_REVOKED":
            revoke_session(session)
            audit.stage("auth.session.rejected", "denied", actor_id=session.user_id, subject_id=session.user_id,
                        resource_type="session", resource_id=session.id, reason_code=reason)
            audit.commit()
        return
    if now - session.last_seen_at >= LAST_SEEN_RESOLUTION:
        session.last_seen_at = now
        db.session.commit()
    g.session = session
    g.user = session.user


def _origin_allowed(origin):
    if origin in current_app.config["ALLOWED_ORIGINS"]:
        return True
    return origin.rstrip("/") == request.host_url.rstrip("/")


def csrf_protect():
    """before_request hook (after load_session) for unsafe API methods."""
    if request.method not in UNSAFE_METHODS or not request.path.startswith("/api/"):
        return
    origin = request.headers.get("Origin")
    if origin and not _origin_allowed(origin):
        raise ApiError(403, "CSRF_ORIGIN_REJECTED", "Request origin is not allowed.")
    if g.session is not None:
        sent = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(sent.encode("utf-8"), g.session.csrf_token.encode("utf-8")):
            raise ApiError(403, "CSRF_TOKEN_INVALID", "Missing or invalid CSRF token. Refresh the page and retry.")


def _deny(status, code, message, reason):
    audit.record("authz.denied", "denied", actor_id=g.user.id if g.user else None,
                 resource_type="endpoint", resource_id=request.endpoint, action=request.method,
                 reason_code=reason, details={"path": request.path})
    raise ApiError(status, code, message)


def deny_investigator_without_mfa():
    _deny(403, "MFA_ENROLLMENT_REQUIRED",
          "Investigators must enable and verify multi-factor authentication first.", "MFA_NOT_ENROLLED")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None:
            _deny(401, "AUTHENTICATION_REQUIRED", "Please sign in.", g.session_rejection or "UNAUTHENTICATED")
        if g.session.mfa_pending:
            _deny(401, "MFA_REQUIRED", "Multi-factor verification is required.", "MFA_PENDING")
        return view(*args, **kwargs)

    return wrapper


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(*args, **kwargs):
            if g.user.role not in roles:
                _deny(403, "FORBIDDEN", "You do not have permission to perform this action.", "ROLE_NOT_PERMITTED")
            if not investigator_mfa_satisfied(g.user, g.session):
                deny_investigator_without_mfa()
            return view(*args, **kwargs)

        return wrapper

    return decorator


def investigator_mfa_satisfied(user, session):
    if user.role != "investigator" or not current_app.config["REQUIRE_MFA_FOR_INVESTIGATORS"]:
        return True
    return bool(user.mfa_enabled and session.mfa_verified)


def pending_mfa_required(view):
    """Allows only a session that has passed the password step and awaits MFA."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None or not g.session.mfa_pending:
            raise ApiError(401, "NO_PENDING_MFA", "No sign-in is awaiting verification. Please sign in again.")
        return view(*args, **kwargs)

    return wrapper


def apply_session_cookie(response):
    """after_request hook: set or clear the session cookie."""
    cfg = current_app.config
    name = cfg["SESSION_COOKIE_NAME"]
    token = g.get("new_session_token")
    if token:
        response.set_cookie(
            name, token, httponly=True, secure=cfg["COOKIE_SECURE"], samesite="Strict", path="/",
            max_age=cfg["SESSION_ABSOLUTE_HOURS"] * 3600,
        )
    elif g.get("clear_session_cookie"):
        response.delete_cookie(name, path="/", secure=cfg["COOKIE_SECURE"], httponly=True, samesite="Strict")
    return response
