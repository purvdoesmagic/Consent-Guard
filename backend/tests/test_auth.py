from datetime import timedelta

import pyotp
import pytest

from app import create_app
from app.extensions import db, limiter
from app.models import AuditEvent, RecoveryCode, User, UserSession
from app.security.crypto import generate_key_b64
from app.utils import time as time_utils
from tests.conftest import PASSWORD, ApiClient, enable_mfa, make_user


def test_register_and_login(api):
    c = api()
    resp = c.register("alice")
    assert resp.status_code == 201
    assert resp.get_json()["user"]["role"] == "subject"
    resp = c.login("alice")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["authenticated"] is True and body["mfa_required"] is False
    assert body["csrf_token"]
    me = c.get("/api/auth/me")
    assert me.status_code == 200 and me.get_json()["user"]["username"] == "alice"


def test_session_cookie_flags(api):
    c = api()
    c.register("alice")
    resp = c.login("alice")
    cookie = resp.headers["Set-Cookie"]
    assert "cg_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Path=/" in cookie


def test_password_is_hashed_with_argon2id(api, app):
    api().register("alice")
    user = User.query.filter_by(username="alice").one()
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash


def test_session_token_stored_only_as_hash(api):
    c = api()
    c.register("alice")
    c.login("alice")
    token = c.http.get_cookie("cg_session").value
    stored = UserSession.query.one()
    assert stored.token_hash != token and len(stored.token_hash) == 64


def test_register_rejects_weak_password_and_duplicate(api):
    c = api()
    resp = c.register("alice", password="short")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["details"]["field"] == "password"
    assert c.register("alice").status_code == 201
    dup = c.register("ALICE")
    assert dup.status_code == 400 and dup.get_json()["error"]["details"]["field"] == "username"


def test_register_cannot_self_assign_investigator(api):
    resp = api().register("mallory", role="investigator")
    assert resp.status_code == 400
    assert User.query.filter_by(username="mallory").first() is None


def test_invalid_credentials_are_generic_and_logged(api):
    c = api()
    c.register("alice")
    wrong = c.login("alice", "Wrong-Password-99!")
    unknown = c.login("nobody", "Wrong-Password-99!")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json()["error"]["message"] == unknown.get_json()["error"]["message"]
    failures = AuditEvent.query.filter_by(event_type="auth.login.failure").all()
    assert {f.reason_code for f in failures} == {"INVALID_CREDENTIALS", "UNKNOWN_ACCOUNT"}
    for f in failures:
        assert "Wrong-Password" not in f.details_json


def test_logout_invalidates_session(api):
    c = make_user(api, "alice")
    old_cookie = c.http.get_cookie("cg_session").value
    assert c.post("/api/auth/logout").status_code == 200
    assert c.get("/api/auth/me").status_code == 401
    # Replaying the old cookie after logout must fail.
    replay = api()
    replay.http.set_cookie("cg_session", old_cookie)
    assert replay.get("/api/auth/me").status_code == 401


def test_session_idle_timeout(api, monkeypatch):
    c = make_user(api, "alice")
    real_now = time_utils.utcnow()
    monkeypatch.setattr("app.security.sessions.utcnow", lambda: real_now + timedelta(minutes=31))
    resp = c.get("/api/auth/me")
    assert resp.status_code == 401
    assert AuditEvent.query.filter_by(event_type="auth.session.rejected", reason_code="SESSION_IDLE_TIMEOUT").count() == 1


def test_session_absolute_expiry(api, monkeypatch):
    c = make_user(api, "alice")
    real_now = time_utils.utcnow()
    monkeypatch.setattr("app.security.sessions.utcnow", lambda: real_now + timedelta(hours=9))
    assert c.get("/api/auth/me").status_code == 401


def test_state_change_requires_csrf_token(api):
    c = make_user(api, "alice")
    resp = c.http.post("/api/auth/logout", json={})  # no X-CSRF-Token header
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "CSRF_TOKEN_INVALID"
    assert c.get("/api/auth/me").status_code == 200  # still logged in


def test_foreign_origin_rejected(api):
    c = api()
    resp = c.http.post("/api/auth/login", json={"username": "x", "password": "y"},
                       headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403
    assert resp.get_json()["error"]["code"] == "CSRF_ORIGIN_REJECTED"


def test_mfa_enrollment_and_login(api):
    c = make_user(api, "alice")
    secret, codes = enable_mfa(c)
    assert len(codes) == 10
    user = User.query.filter_by(username="alice").one()
    assert user.mfa_enabled and secret not in (user.mfa_secret_enc or "")
    c.post("/api/auth/logout")

    c2 = api()
    first = c2.login("alice").get_json()
    assert first["mfa_required"] is True
    # A pending-MFA session cannot use the API.
    assert c2.get("/api/auth/me").status_code == 401
    bad = c2.post("/api/auth/mfa/verify", {"code": "000000"})
    assert bad.status_code == 401
    # A code different from the one used at enrollment (next time-step).
    import time

    code = pyotp.TOTP(secret).at(int(time.time()) + 30)
    ok = c2.post("/api/auth/mfa/verify", {"code": code})
    assert ok.status_code == 200, ok.get_json()
    assert ok.get_json()["authenticated"] is True
    assert c2.get("/api/auth/me").status_code == 200


def test_totp_code_cannot_be_replayed(api):
    c = make_user(api, "alice")
    secret = c.post("/api/auth/mfa/setup").get_json()["secret"]
    used_code = pyotp.TOTP(secret).now()
    assert c.post("/api/auth/mfa/enable", {"code": used_code}).status_code == 200
    c.post("/api/auth/logout")
    c2 = api()
    c2.login("alice")
    # Replaying the exact code consumed at enrollment must fail, even within its validity window.
    resp = c2.post("/api/auth/mfa/verify", {"code": used_code})
    assert resp.status_code == 401


def test_recovery_code_single_use(api):
    c = make_user(api, "alice")
    _, codes = enable_mfa(c)
    c.post("/api/auth/logout")

    c2 = api()
    c2.login("alice")
    assert c2.post("/api/auth/mfa/verify", {"recovery_code": codes[0]}).status_code == 200
    assert RecoveryCode.query.filter(RecoveryCode.used_at.isnot(None)).count() == 1
    c2.post("/api/auth/logout")

    c3 = api()
    c3.login("alice")
    assert c3.post("/api/auth/mfa/verify", {"recovery_code": codes[0]}).status_code == 401
    assert c3.post("/api/auth/mfa/verify", {"recovery_code": codes[1].lower()}).status_code == 200


def test_mfa_verify_rotates_session_token(api):
    c = make_user(api, "alice")
    _, codes = enable_mfa(c)
    c.post("/api/auth/logout")
    c2 = api()
    c2.login("alice")
    pending_token = c2.http.get_cookie("cg_session").value
    c2.post("/api/auth/mfa/verify", {"recovery_code": codes[0]})
    assert c2.http.get_cookie("cg_session").value != pending_token
    stale = api()
    stale.http.set_cookie("cg_session", pending_token)
    assert stale.get("/api/auth/me").status_code == 401


def test_password_change_revokes_other_sessions(api):
    a1 = make_user(api, "alice")
    a2 = api()
    a2.login("alice")
    resp = a1.post("/api/auth/password", {"current_password": PASSWORD, "new_password": "Another-Strong-Pass-7"})
    assert resp.status_code == 200 and resp.get_json()["sessions_revoked"] == 1
    assert a2.get("/api/auth/me").status_code == 401
    assert a1.get("/api/auth/me").status_code == 200


def test_login_rate_limit(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'rl.db').as_posix()}",
        "ENCRYPTION_KEY": generate_key_b64(),
        "RATELIMIT_ENABLED": True,
        "LOGIN_RATE_LIMIT": "3 per minute",
        "ARGON2_TIME_COST": 1, "ARGON2_MEMORY_COST": 8192,
    })
    with app.app_context():
        db.create_all()
        limiter.reset()
        c = ApiClient(app)
        codes = [c.login("ghost", "Wrong-Password-99!").status_code for _ in range(4)]
        assert codes == [401, 401, 401, 429]
        assert c.login("ghost").get_json()["error"]["code"] == "RATE_LIMITED"
        limiter.reset()
        db.session.remove()
        db.engine.dispose()


def test_mfa_verify_rate_limit(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'rl2.db').as_posix()}",
        "ENCRYPTION_KEY": generate_key_b64(),
        "RATELIMIT_ENABLED": True,
        "MFA_RATE_LIMIT": "3 per minute",
        "ARGON2_TIME_COST": 1, "ARGON2_MEMORY_COST": 8192,
    })
    with app.app_context():
        db.create_all()
        limiter.reset()
        c = ApiClient(app)
        c.register("alice")
        c.login("alice")
        enable_mfa(c)
        c.post("/api/auth/logout")
        c2 = ApiClient(app)
        c2.login("alice")
        codes = [c2.post("/api/auth/mfa/verify", {"code": "000000"}).status_code for _ in range(4)]
        assert codes == [401, 401, 401, 429]
        limiter.reset()
        db.session.remove()
        db.engine.dispose()
