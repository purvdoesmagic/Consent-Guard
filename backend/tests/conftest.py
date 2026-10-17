"""Shared pytest fixtures.

Each test gets a brand-new SQLite database in pytest's temporary directory
and a freshly generated encryption key, so tests never touch the
development database or the developer's .env file.
"""

import pyotp
import pytest

from app import create_app
from app.extensions import db
from app.security.crypto import generate_key_b64

PASSWORD = "Correct-Horse-42!"


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
        "ENCRYPTION_KEY": generate_key_b64(),
        "ENCRYPTION_KEY_ID": "test-k1",
        "RATELIMIT_ENABLED": False,
        "ARGON2_TIME_COST": 1,
        "ARGON2_MEMORY_COST": 8192,
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


class ApiClient:
    """Test helper that behaves like the frontend: keeps cookies and sends
    the CSRF header on state-changing requests."""

    def __init__(self, app):
        self.http = app.test_client()
        self.csrf = None

    def _headers(self, extra=None):
        headers = {}
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        headers.update(extra or {})
        return headers

    def get(self, url, **kw):
        return self.http.get(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def post(self, url, json=None, **kw):
        resp = self.http.post(url, json=json if json is not None else {}, headers=self._headers(kw.pop("headers", None)), **kw)
        self._capture(resp)
        return resp

    def patch(self, url, json=None, **kw):
        return self.http.patch(url, json=json or {}, headers=self._headers(kw.pop("headers", None)), **kw)

    def delete(self, url, **kw):
        return self.http.delete(url, headers=self._headers(kw.pop("headers", None)), **kw)

    def _capture(self, resp):
        if resp.is_json and isinstance(resp.get_json(), dict) and resp.get_json().get("csrf_token"):
            self.csrf = resp.get_json()["csrf_token"]

    def register(self, username, role="subject", password=PASSWORD, display_name=None):
        return self.post("/api/auth/register", {
            "username": username, "password": password, "role": role,
            "display_name": display_name or username.title(),
        })

    def login(self, username, password=PASSWORD):
        return self.post("/api/auth/login", {"username": username, "password": password})


@pytest.fixture
def api(app):
    return lambda: ApiClient(app)


def make_user(api_factory, username, role="subject"):
    """Register (via API or CLI-equivalent service for investigators) and log in."""
    client = api_factory()
    if role == "investigator":
        from app.services.users import create_user

        create_user(username, PASSWORD, username.title(), "investigator")
    else:
        assert client.register(username, role).status_code == 201
    assert client.login(username).status_code == 200
    return client


def enable_mfa(client):
    """Enroll TOTP for the logged-in client and return the base32 secret."""
    setup = client.post("/api/auth/mfa/setup").get_json()
    secret = setup["secret"]
    resp = client.post("/api/auth/mfa/enable", {"code": pyotp.TOTP(secret).now()})
    assert resp.status_code == 200, resp.get_json()
    return secret, resp.get_json()["recovery_codes"]
