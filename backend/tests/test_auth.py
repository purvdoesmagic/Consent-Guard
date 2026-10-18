import pyotp

from conftest import login
from models import LogEntry, User


def test_register_and_login(client):
    res = client.post("/api/register", json={"username": "carol", "name": "Carol", "password": "longpassword",
                                             "role": "user"})
    assert res.status_code == 201
    assert client.post("/api/login", json={"username": "carol", "password": "longpassword"}).status_code == 200
    assert client.get("/api/me").get_json()["user"]["username"] == "carol"


def test_password_is_not_stored_in_plain_text(client):
    client.post("/api/register", json={"username": "carol", "name": "Carol", "password": "longpassword",
                                       "role": "user"})
    assert "longpassword" not in User.query.filter_by(username="carol").first().password_hash


def test_cannot_register_as_investigator(client):
    res = client.post("/api/register", json={"username": "eve", "name": "Eve", "password": "longpassword",
                                             "role": "investigator"})
    assert res.status_code == 400


def test_wrong_password_is_rejected_and_logged(client, users):
    res = client.post("/api/login", json={"username": "alice", "password": "wrong-password"})
    assert res.status_code == 401
    assert LogEntry.query.filter_by(action="login", result="failed", target="alice").count() == 1


def test_login_blocked_after_too_many_wrong_passwords(client, users):
    for _ in range(5):
        client.post("/api/login", json={"username": "alice", "password": "wrong-password"})
    assert login(client, "alice").status_code == 429


def test_logout(client, users):
    login(client, "alice")
    client.post("/api/logout")
    assert client.get("/api/me").get_json()["user"] is None
    assert client.get("/api/consents").status_code == 401


def test_two_step_login(client, users):
    login(client, "alice")
    secret = client.post("/api/two-step/setup").get_json()["secret"]
    assert client.post("/api/two-step/enable", json={"code": pyotp.TOTP(secret).now()}).status_code == 200
    client.post("/api/logout")

    res = login(client, "alice")
    assert res.status_code == 401 and res.get_json()["need_code"]
    assert login(client, "alice", code="000000").status_code == 401
    assert login(client, "alice", code=pyotp.TOTP(secret).now()).status_code == 200
