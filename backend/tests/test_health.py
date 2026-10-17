from app import create_app
from app.security.crypto import KeyConfigurationError

import pytest


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["time"].endswith("Z")


def test_security_headers_present(client):
    resp = client.get("/api/health")
    assert "default-src 'self'" in resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Cache-Control"] == "no-store"
    assert resp.headers["X-Request-ID"]


def test_unknown_api_route_returns_json_404(client):
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.get_json()["error"]["code"] == "NOT_FOUND"


def test_app_refuses_to_start_without_key(tmp_path):
    with pytest.raises(KeyConfigurationError):
        create_app({"TESTING": True, "ENCRYPTION_KEY": None,
                    "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'x.db').as_posix()}"})
