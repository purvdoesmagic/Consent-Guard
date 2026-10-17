from datetime import timedelta

from app.extensions import db
from app.models import AuditEvent, Consent, ConsentVersion, User
from tests.helpers import grant, read, setup_parties, shift_time


def test_create_consent_records_history_and_audit(api):
    alice, acme, _, acme_id, _ = setup_parties(api)
    consent = grant(alice, acme_id, categories=("health", "contact"))
    assert consent["status"] == "active"
    assert consent["categories"] == ["contact", "health"]
    assert consent["history"][0]["change_type"] == "created"
    assert AuditEvent.query.filter_by(event_type="consent.created", consent_id=consent["id"]).count() == 1


def test_consent_validation(api):
    alice, acme, bob, acme_id, _ = setup_parties(api)
    bob_id = User.query.filter_by(username="bob").one().id
    bad_purpose = alice.post("/api/consents", {"recipient_id": acme_id, "purpose": "spying", "categories": ["health"]})
    assert bad_purpose.status_code == 400
    bad_cat = alice.post("/api/consents", {"recipient_id": acme_id, "purpose": "marketing", "categories": ["dna"]})
    assert bad_cat.status_code == 400
    not_processor = alice.post("/api/consents", {"recipient_id": bob_id, "purpose": "marketing", "categories": ["contact"]})
    assert not_processor.status_code == 400
    past = alice.post("/api/consents", {"recipient_id": acme_id, "purpose": "marketing", "categories": ["contact"],
                                        "expires_at": "2020-01-01T00:00:00Z"})
    assert past.status_code == 400


def test_duplicate_active_consent_rejected(api):
    alice, _, _, acme_id, _ = setup_parties(api)
    grant(alice, acme_id)
    dup = alice.post("/api/consents", {"recipient_id": acme_id, "purpose": "medical_research", "categories": ["health"]})
    assert dup.status_code == 409


def test_only_subjects_create_consent(api):
    _, acme, _, acme_id, _ = setup_parties(api)
    resp = acme.post("/api/consents", {"recipient_id": acme_id, "purpose": "marketing", "categories": ["contact"]})
    assert resp.status_code == 403


def test_update_consent_categories_and_expiry(api):
    alice, _, _, acme_id, _ = setup_parties(api)
    consent = grant(alice, acme_id)
    resp = alice.patch(f"/api/consents/{consent['id']}", {"categories": ["health", "demographic"]})
    assert resp.status_code == 200
    body = resp.get_json()["consent"]
    assert body["version"] == 2 and body["categories"] == ["demographic", "health"]
    assert [h["change_type"] for h in body["history"]] == ["created", "updated"]
    assert alice.patch(f"/api/consents/{consent['id']}", {"categories": ["demographic", "health"]}).status_code == 400


def test_purpose_and_recipient_are_immutable(api):
    alice, _, _, acme_id, _ = setup_parties(api)
    consent = grant(alice, acme_id)
    resp = alice.patch(f"/api/consents/{consent['id']}", {"purpose": "marketing"})
    assert resp.status_code == 400


def test_withdraw_and_invalid_transitions(api):
    alice, _, _, acme_id, _ = setup_parties(api)
    consent = grant(alice, acme_id)
    resp = alice.post(f"/api/consents/{consent['id']}/withdraw")
    assert resp.status_code == 200
    body = resp.get_json()["consent"]
    assert body["status"] == "withdrawn" and body["withdrawn_at"]
    # Withdrawn is terminal.
    assert alice.post(f"/api/consents/{consent['id']}/withdraw").status_code == 409
    assert alice.patch(f"/api/consents/{consent['id']}", {"categories": ["contact"]}).status_code == 409
    assert AuditEvent.query.filter_by(event_type="consent.withdraw_rejected").count() == 1
    # A new consent for the same purpose is allowed after withdrawal.
    assert grant(alice, acme_id)["status"] == "active"


def test_consent_expires_lazily(api, monkeypatch):
    alice, acme, _, acme_id, record = setup_parties(api)
    consent = grant(alice, acme_id, expires_in=timedelta(minutes=5))
    assert read(acme, record["id"]).status_code == 200
    shift_time(monkeypatch, timedelta(minutes=6))
    detail = alice.get(f"/api/consents/{consent['id']}").get_json()["consent"]
    assert detail["status"] == "expired"
    assert detail["history"][-1]["change_type"] == "expired"
    assert detail["history"][-1]["changed_by"] is None
    assert AuditEvent.query.filter_by(event_type="consent.expired").count() == 1
    assert alice.patch(f"/api/consents/{consent['id']}", {"categories": ["contact"]}).status_code == 409


def test_expiry_boundary_is_inclusive(api, monkeypatch):
    """At exactly expires_at the consent is already expired."""
    alice, acme, _, acme_id, record = setup_parties(api)
    consent = grant(alice, acme_id, expires_in=timedelta(minutes=5))
    expires = db.session.get(Consent, consent["id"]).expires_at
    for target in ("app.services.consent.utcnow", "app.services.authorization.utcnow"):
        monkeypatch.setattr(target, lambda: expires - timedelta(microseconds=1))
    assert read(acme, record["id"]).status_code == 200
    for target in ("app.services.consent.utcnow", "app.services.authorization.utcnow"):
        monkeypatch.setattr(target, lambda: expires)
    resp = read(acme, record["id"])
    assert resp.status_code == 403 and resp.get_json()["error"]["details"]["reason"] == "DENY_CONSENT_EXPIRED"


def test_consent_versions_are_append_only_snapshots(api):
    alice, _, _, acme_id, _ = setup_parties(api)
    consent = grant(alice, acme_id)
    alice.patch(f"/api/consents/{consent['id']}", {"categories": ["health", "contact"]})
    alice.post(f"/api/consents/{consent['id']}/withdraw")
    versions = ConsentVersion.query.filter_by(consent_id=consent["id"]).order_by(ConsentVersion.version).all()
    assert [v.version for v in versions] == [1, 2, 3]
    assert versions[0].categories == ["health"]
    assert versions[2].status == "withdrawn"
