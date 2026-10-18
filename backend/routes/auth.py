"""Register, log in, log out and two-step login (6-digit code from a phone app)."""

import io
from datetime import timedelta
from functools import wraps

import pyotp
import segno
from flask import Blueprint, current_app, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from audit_log import add_log
from encryption import decrypt, encrypt
from models import LogEntry, User, db, now

bp = Blueprint("auth", __name__, url_prefix="/api")


def current_user():
    user_id = session.get("user_id")
    return db.session.get(User, user_id) if user_id else None


def login_required(*roles):
    """Decorator: the route only runs for a logged-in user with one of `roles`.
    The user is passed to the route as the first argument."""
    def decorator(route):
        @wraps(route)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return {"error": "Please log in first."}, 401
            if roles and user.role not in roles:
                add_log("access", "denied", user_id=user.id, target=request.path, reason="WRONG_ROLE")
                return {"error": "You are not allowed to do this."}, 403
            return route(user, *args, **kwargs)
        return wrapper
    return decorator


def too_many_failed_logins(username):
    minutes = current_app.config["LOCKOUT_MINUTES"]
    since = (now() - timedelta(minutes=minutes)).isoformat()
    failed = LogEntry.query.filter(
        LogEntry.action == "login", LogEntry.result == "failed",
        LogEntry.target == username, LogEntry.time >= since,
    ).count()
    return failed >= current_app.config["MAX_FAILED_LOGINS"]


@bp.post("/register")
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    name = (data.get("name") or "").strip()
    password = data.get("password") or ""
    role = data.get("role")

    if not username.isalnum() or not 3 <= len(username) <= 30:
        return {"error": "Username must be 3-30 letters or numbers."}, 400
    if not name:
        return {"error": "Please enter your name."}, 400
    if len(password) < 8:
        return {"error": "Password must be at least 8 characters."}, 400
    if role not in ("user", "company"):  # investigators are created by seed.py only
        return {"error": "Role must be user or company."}, 400
    if User.query.filter_by(username=username).first():
        return {"error": "That username is taken."}, 400

    user = User(username=username, name=name, role=role, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    add_log("register", "success", user_id=user.id, target=username)
    return {"user": user.to_dict()}, 201


@bp.post("/login")
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""
    code = (data.get("code") or "").strip()

    if too_many_failed_logins(username):
        return {"error": "Too many wrong attempts. Please wait a few minutes."}, 429

    user = User.query.filter_by(username=username).first()
    if user is None or not check_password_hash(user.password_hash, password):
        add_log("login", "failed", user_id=user.id if user else None, target=username, reason="WRONG_PASSWORD")
        return {"error": "Wrong username or password."}, 401

    if user.totp_secret:
        if not code:
            return {"error": "Enter the 6-digit code from your authenticator app.", "need_code": True}, 401
        if not pyotp.TOTP(decrypt(user.totp_secret)).verify(code, valid_window=1):
            add_log("login", "failed", user_id=user.id, target=username, reason="WRONG_CODE")
            return {"error": "Wrong code. Please try again.", "need_code": True}, 401

    session.clear()
    session["user_id"] = user.id
    session.permanent = True  # expires after PERMANENT_SESSION_LIFETIME
    add_log("login", "success", user_id=user.id, target=username)
    return {"user": user.to_dict()}


@bp.post("/logout")
def logout():
    user = current_user()
    if user:
        add_log("logout", "success", user_id=user.id, target=user.username)
    session.clear()
    return {"message": "Logged out."}


@bp.get("/me")
def me():
    user = current_user()
    if user is None:
        return {"user": None}
    return {"user": user.to_dict()}


@bp.post("/two-step/setup")
@login_required()
def two_step_setup(user):
    """Create a secret and a QR code to scan with Google/Microsoft Authenticator."""
    secret = pyotp.random_base32()
    session["pending_secret"] = secret
    link = pyotp.TOTP(secret).provisioning_uri(name=user.username, issuer_name="ConsentGuard")
    svg = io.BytesIO()
    segno.make(link).save(svg, kind="svg", scale=5)
    return {"secret": secret, "qr_svg": svg.getvalue().decode("utf-8")}


@bp.post("/two-step/enable")
@login_required()
def two_step_enable(user):
    secret = session.get("pending_secret")
    code = ((request.get_json() or {}).get("code") or "").strip()
    if not secret:
        return {"error": "Start the setup first."}, 400
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        return {"error": "Wrong code. Please try again."}, 400
    user.totp_secret = encrypt(secret)
    db.session.commit()
    session.pop("pending_secret")
    add_log("two_step.enable", "success", user_id=user.id, target=user.username)
    return {"user": user.to_dict()}
