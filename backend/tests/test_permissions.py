from datetime import timedelta

from conftest import login
from models import Consent, Record, db, now
from seed import give_consent, make_record, make_user, withdraw


def view(client, record, purpose):
    return client.post(f"/api/records/{record.id}/view", json={"purpose": purpose})


def test_company_can_view_with_permission(client, users):
    record = make_record(users["alice"], "Blood test", "health", "secret result")
    give_consent(users["alice"], users["acme"], "research", ["health"])
    login(client, "acme")
    res = view(client, record, "research")
    assert res.status_code == 200
    assert res.get_json()["content"] == "secret result"


def test_blocked_without_permission(client, users):
    record = make_record(users["alice"], "Blood test", "health", "secret result")
    login(client, "acme")
    res = view(client, record, "research")
    assert res.status_code == 403
    assert res.get_json()["reason"] == "NO_CONSENT"
    assert "secret result" not in res.get_data(as_text=True)


def test_blocked_for_wrong_purpose(client, users):
    record = make_record(users["alice"], "Blood test", "health", "x")
    give_consent(users["alice"], users["acme"], "research", ["health"])
    login(client, "acme")
    assert view(client, record, "marketing").get_json()["reason"] == "WRONG_PURPOSE"


def test_blocked_for_wrong_category(client, users):
    record = make_record(users["alice"], "Bank summary", "financial", "x")
    give_consent(users["alice"], users["acme"], "research", ["health"])
    login(client, "acme")
    assert view(client, record, "research").get_json()["reason"] == "CATEGORY_NOT_ALLOWED"


def test_blocked_after_withdrawal(client, users):
    record = make_record(users["alice"], "Blood test", "health", "x")
    consent = give_consent(users["alice"], users["acme"], "research", ["health"])
    withdraw(consent)
    login(client, "acme")
    assert view(client, record, "research").get_json()["reason"] == "CONSENT_WITHDRAWN"


def test_blocked_after_expiry(client, users):
    record = make_record(users["alice"], "Blood test", "health", "x")
    consent = give_consent(users["alice"], users["acme"], "research", ["health"])
    consent.expires_at = now() - timedelta(seconds=1)
    db.session.commit()
    login(client, "acme")
    assert view(client, record, "research").get_json()["reason"] == "CONSENT_EXPIRED"
    assert db.session.get(Consent, consent.id).status == "expired"


def test_user_gives_and_withdraws_permission(client, users):
    login(client, "alice")
    res = client.post("/api/consents", json={"company_id": users["acme"].id, "purpose": "research",
                                             "categories": ["health"], "days": 30})
    assert res.status_code == 201
    consent_id = res.get_json()["consent"]["id"]
    assert client.post(f"/api/consents/{consent_id}/withdraw").get_json()["consent"]["status"] == "withdrawn"
    assert client.post(f"/api/consents/{consent_id}/withdraw").status_code == 400  # can't withdraw twice


def test_user_cannot_withdraw_someone_elses_permission(client, users):
    bob = make_user("bob", "Bob", "user")
    consent = give_consent(bob, users["acme"], "research", ["health"])
    login(client, "alice")
    assert client.post(f"/api/consents/{consent.id}/withdraw").status_code == 404


def test_company_cannot_give_permission(client, users):
    login(client, "acme")
    res = client.post("/api/consents", json={"company_id": users["acme"].id, "purpose": "research",
                                             "categories": ["health"]})
    assert res.status_code == 403


def test_investigator_cannot_read_personal_data(client, users):
    record = make_record(users["alice"], "Blood test", "health", "x")
    login(client, "ivy")
    assert view(client, record, "research").status_code == 403


def test_content_is_encrypted_in_database(client, users):
    login(client, "alice")
    client.post("/api/records", json={"title": "Notes", "category": "health", "content": "very private"})
    stored = Record.query.first().encrypted_content
    assert "very private" not in stored
