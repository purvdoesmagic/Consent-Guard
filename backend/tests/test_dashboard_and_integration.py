"""Dashboard statistics and complete user journeys through the real API."""

from datetime import timedelta

import pyotp

from tests.conftest import ApiClient, enable_mfa, make_user
from tests.helpers import grant, read, setup_parties, shift_time


def test_dashboard_counts_reflect_real_data(api, monkeypatch):
    alice, acme, _, acme_id, record = setup_parties(api)
    c1 = grant(alice, acme_id)
    grant(alice, acme_id, purpose="analytics", categories=("demographic",), expires_in=timedelta(minutes=2))
    grant(alice, acme_id, purpose="marketing", categories=("contact",))
    read(acme, record["id"])
    alice.post(f"/api/consents/{c1['id']}/withdraw")
    read(acme, record["id"])

    dash = alice.get("/api/dashboard").get_json()
    assert dash["consents"] == {"active": 2, "withdrawn": 1, "expired": 0}
    assert dash["access"]["allowed"] == 1 and dash["access"]["denied"] == 1
    assert dash["open_cases"] is None
    assert dash["integrity"]["valid"] is True and dash["recent_events"]

    shift_time(monkeypatch, timedelta(minutes=3))
    later = alice.get("/api/dashboard").get_json()
    assert later["consents"] == {"active": 1, "withdrawn": 1, "expired": 1}

    acme_dash = acme.get("/api/dashboard").get_json()
    assert acme_dash["access"]["total"] == 2


def test_api_error_shapes(api):
    c = make_user(api, "alice")
    not_json = c.http.post("/api/consents", data="x", headers={"X-CSRF-Token": c.csrf, "Content-Type": "text/plain"})
    assert not_json.status_code == 415 and not_json.get_json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    bad = c.post("/api/consents", {"recipient_id": "one"})
    err = bad.get_json()["error"]
    assert bad.status_code == 400 and err["code"] == "VALIDATION_ERROR" and err["request_id"]
    big = c.http.post("/api/records", data="x" * 70000, headers={"X-CSRF-Token": c.csrf,
                                                                   "Content-Type": "application/json"})
    assert big.status_code == 413


def test_full_privacy_investigation_journey(api):
    # 1. Subject registers, enables MFA, logs in with TOTP.
    alice = make_user(api, "alice")
    secret, _ = enable_mfa(alice)
    acme = make_user(api, "acme", role="processor")
    alice.post("/api/auth/logout")
    alice = ApiClient(alice.http.application)
    assert alice.login("alice").get_json()["mfa_required"] is True
    import time

    assert alice.post("/api/auth/mfa/verify", {"code": pyotp.TOTP(secret).at(int(time.time()) + 30)}).status_code == 200

    # 2. Subject creates a synthetic record and grants consent.
    record = alice.post("/api/records", {"label": "Synthetic GP summary", "category": "health",
                                         "fields": {"Summary": "SYNTHETIC"}}).get_json()["record"]
    acme_id = next(p["id"] for p in alice.get("/api/processors").get_json()["processors"] if p["username"] == "acme")
    consent = grant(alice, acme_id)

    # 3. Processor reads under consent, then subject withdraws, processor retries.
    assert read(acme, record["id"]).status_code == 200
    alice.post(f"/api/consents/{consent['id']}/withdraw")
    assert read(acme, record["id"]).status_code == 403

    # 4. Investigator opens a case, links evidence, sees indicators, verifies chain, downloads report.
    inv = make_user(api, "ivy", role="investigator")
    enable_mfa(inv)
    denied = inv.get("/api/audit/events?outcome=denied&event_type=record.access").get_json()["events"]
    case = inv.post("/api/cases", {"title": "Withdrawal follow-up"}).get_json()["case"]
    inv.post(f"/api/cases/{case['id']}/events", {"event_ids": [e["event_id"] for e in denied]})
    indicators = inv.get(f"/api/cases/{case['id']}/indicators").get_json()["indicators"]
    assert indicators[0]["rule_code"] == "ACCESS_AFTER_WITHDRAWAL"
    assert inv.post("/api/audit/verify").get_json()["valid"] is True
    pdf = inv.get(f"/api/cases/{case['id']}/report.pdf")
    assert pdf.status_code == 200 and pdf.data[:5] == b"%PDF-"
    assert inv.get("/api/dashboard").get_json()["open_cases"] == 1
