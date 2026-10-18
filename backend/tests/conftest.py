import base64
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from models import db  # noqa: E402
from seed import DEMO_PASSWORD, make_user  # noqa: E402


@pytest.fixture
def app(tmp_path):
    """A fresh app with its own empty database and key for every test."""
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'test.db'}",
        "ENCRYPTION_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "SECRET_KEY": "test",
    })
    with app.app_context():
        yield app
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def users(app):
    return {
        "alice": make_user("alice", "Alice", "user"),
        "acme": make_user("acme", "Acme", "company"),
        "ivy": make_user("ivy", "Ivy", "investigator"),
    }


def login(client, username, **extra):
    return client.post("/api/login", json={"username": username, "password": DEMO_PASSWORD, **extra})
