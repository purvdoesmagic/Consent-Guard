"""Backend authorization: consent rules, cross-user access and direct API bypass attempts."""

from app.models import AuditEvent
from tests.conftest import make_user
from tests.helpers import grant, read, setup_parties


def reason(resp):
    return resp.get_json()["error"]["details"]["reason"]


def test_anonymous_requests_are_rejected(client):
    for method, url in [("get", "/api/consents"), ("get", "/api/records"), ("get", "/api/auth/me"),
                        ("post", "/api/records/abc/access"), ("get", "/api/audit/events"),
                        ("get", "/api/cases"), ("get", "/api/dashboard")]:
        resp = getattr(client, method)(url, json={} if method == "post" else None)
        assert resp.status_code == 401, (method, url, resp.status_code)


def test_owner_can_read_own_record(api):
    alice, _, _, _, record = setup_parties(api)
    resp = read(alice, record["id"], purpose=None)
    assert resp.status_code == 200
    assert resp.get_json()["decision"] == "ALLOW_OWNER"
    assert resp.get_json()["payload"]["Glucose"] == "5.1 mmol/L"


def test_processor_with_matching_consent_allowed(api):
    alice, acme, _, acme_id, record = setup_parties(api)
    consent = grant(alice, acme_id)
    resp = read(acme, record["id"])
    assert resp.status_code == 200
    assert resp.get_json()["consent_id"] == consent["id"]
    event = AuditEvent.query.filter_by(event_type="record.access", outcome="allowed", actor_id=2).one()
    assert event.consent_id == consent["id"] and event.reason_code == "ALLOW_CONSENT"
    assert "5.1 mmol" not in event.details_json  # plaintext never logged


def test_processor_without_consent_denied_generically(api):
    _, acme, _, _, record = setup_parties(api)
    resp = read(acme, record["id"])
    assert resp.status_code == 403
    assert reason(resp) == "ACCESS_DENIED"  # does not reveal relationship
    event = AuditEvent.query.filter_by(event_type="record.access", outcome="denied").one()
    assert event.reason_code == "DENY_NO_CONSENT"


def test_access_after_withdrawal_denied(api):
    alice, acme, _, acme_id, record = setup_parties(api)
    consent = grant(alice, acme_id)
    assert read(acme, record["id"]).status_code == 200
    alice.post(f"/api/consents/{consent['id']}/withdraw")
    resp = read(acme, record["id"])
    assert resp.status_code == 403 and reason(resp) == "DENY_CONSENT_WITHDRAWN"
    assert "payload" not in resp.get_json()


def test_purpose_mismatch_denied(api):
    alice, acme, _, acme_id, record = setup_parties(api)
    grant(alice, acme_id, purpose="medical_research")
    resp = read(acme, record["id"], purpose="marketing")
    assert resp.status_code == 403 and reason(resp) == "DENY_PURPOSE_NOT_COVERED"


def test_category_mismatch_denied(api):
    alice, acme, _, acme_id, record = setup_parties(api)
    grant(alice, acme_id, purpose="medical_research", categories=("contact",))
    resp = read(acme, record["id"])  # record is "health"
    assert resp.status_code == 403 and reason(resp) == "DENY_CATEGORY_NOT_COVERED"


def test_newer_consent_after_withdrawal_reauthorizes(api):
    alice, acme, _, acme_id, record = setup_parties(api)
    first = grant(alice, acme_id)
    alice.post(f"/api/consents/{first['id']}/withdraw")
    second = grant(alice, acme_id)
    resp = read(acme, record["id"])
    assert resp.status_code == 200 and resp.get_json()["consent_id"] == second["id"]


def test_processor_cannot_export_even_with_consent(api):
    alice, acme, _, acme_id, record = setup_parties(api)
    grant(alice, acme_id)
    resp = read(acme, record["id"], action="export")
    assert resp.status_code == 403 and reason(resp) == "DENY_ACTION_NOT_PERMITTED"


def test_user_a_cannot_read_user_b_record(api):
    _, _, bob, _, record = setup_parties(api)
    resp = read(bob, record["id"], purpose=None)
    assert resp.status_code == 403 and reason(resp) == "ACCESS_DENIED"
    assert AuditEvent.query.filter_by(event_type="record.access", reason_code="DENY_ROLE_NOT_PERMITTED").count() == 1


def test_unknown_record_is_indistinguishable_from_forbidden(api):
    _, acme, _, _, record = setup_parties(api)
    missing = read(acme, "0" * 32)
    forbidden = read(acme, record["id"])
    assert missing.status_code == forbidden.status_code == 403
    assert reason(missing) == reason(forbidden) == "ACCESS_DENIED"


def test_user_a_cannot_view_or_modify_user_b_consent(api):
    alice, _, bob, acme_id, _ = setup_parties(api)
    consent = grant(alice, acme_id)
    assert bob.get(f"/api/consents/{consent['id']}").status_code == 404
    assert bob.patch(f"/api/consents/{consent['id']}", {"categories": ["contact"]}).status_code == 404
    assert bob.post(f"/api/consents/{consent['id']}/withdraw").status_code == 404
    assert alice.get(f"/api/consents/{consent['id']}").get_json()["consent"]["status"] == "active"
    assert all(c["subject"]["username"] == "bob" for c in bob.get("/api/consents").get_json()["consents"])


def test_recipient_can_view_but_not_withdraw(api):
    alice, acme, _, acme_id, _ = setup_parties(api)
    consent = grant(alice, acme_id)
    assert acme.get(f"/api/consents/{consent['id']}").status_code == 200
    assert acme.post(f"/api/consents/{consent['id']}/withdraw").status_code == 403


def test_processor_record_listing_limited_to_consenting_subjects(api):
    alice, acme, bob, acme_id, _ = setup_parties(api)
    bob.post("/api/records", {"label": "Bob synthetic address", "category": "contact", "fields": {"City": "Testville"}})
    assert acme.get("/api/records").get_json()["records"] == []
    grant(alice, acme_id)
    owners = {r["owner"]["username"] for r in acme.get("/api/records").get_json()["records"]}
    assert owners == {"alice"}


def test_investigator_cannot_read_plaintext(api):
    from tests.conftest import enable_mfa

    _, _, _, _, record = setup_parties(api)
    inv = make_user(api, "ivy", role="investigator")
    enable_mfa(inv)
    resp = read(inv, record["id"])
    assert resp.status_code == 403 and reason(resp) == "ACCESS_DENIED"


def test_record_listing_never_contains_ciphertext(api):
    alice, _, _, _, _ = setup_parties(api)
    rec = alice.get("/api/records").get_json()["records"][0]
    assert "ciphertext" not in rec and "nonce" not in rec and "payload" not in rec
