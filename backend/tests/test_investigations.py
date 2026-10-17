import io

from pypdf import PdfReader

from app.extensions import db
from app.models import AuditEvent
from tests.conftest import enable_mfa, make_user
from tests.helpers import grant, read, setup_parties


def investigator(api, username="ivy"):
    client = make_user(api, username, role="investigator")
    enable_mfa(client)
    return client


def scenario(api):
    """Alice grants Acme consent, Acme reads, Alice withdraws, Acme retries 3x."""
    alice, acme, bob, acme_id, record = setup_parties(api)
    consent = grant(alice, acme_id)
    read(acme, record["id"])
    alice.post(f"/api/consents/{consent['id']}/withdraw")
    for _ in range(3):
        read(acme, record["id"])
    return alice, acme, bob, consent, record


def new_case(inv, **extra):
    resp = inv.post("/api/cases", {"title": "Post-withdrawal access by Acme", "description": "Synthetic test case",
                                   **extra})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["case"]


def link_access_events(inv, case_id, consent_id):
    events = inv.get(f"/api/audit/events?consent_id={consent_id}&page_size=200").get_json()["events"]
    ids = [e["event_id"] for e in events]
    resp = inv.post(f"/api/cases/{case_id}/events", {"event_ids": ids, "rationale": "Consent-related activity"})
    assert resp.status_code == 200, resp.get_json()
    return ids


def test_case_creation_and_numbering(api):
    inv = investigator(api)
    first = new_case(inv)
    second = new_case(inv)
    assert first["case_number"].startswith("CG-") and first["case_number"].endswith("0001")
    assert second["case_number"].endswith("0002")
    assert first["status"] == "open"
    assert AuditEvent.query.filter_by(event_type="case.created").count() == 2


def test_non_investigators_cannot_use_cases(api):
    alice, acme, _, _, _ = setup_parties(api)
    for client in (alice, acme):
        assert client.get("/api/cases").status_code == 403
        assert client.post("/api/cases", {"title": "x" * 5}).status_code == 403
        assert client.get("/api/detection/indicators").status_code == 403


def test_investigator_without_mfa_is_blocked(api):
    inv = make_user(api, "ivy", role="investigator")
    resp = inv.get("/api/cases")
    assert resp.status_code == 403 and resp.get_json()["error"]["code"] == "MFA_ENROLLMENT_REQUIRED"


def test_other_investigator_cannot_access_case(api):
    ivy = investigator(api, "ivy")
    zed = investigator(api, "zed")
    case = new_case(ivy)
    assert zed.get(f"/api/cases/{case['id']}").status_code == 404
    assert zed.post(f"/api/cases/{case['id']}/notes", {"note_type": "note", "content": "x"}).status_code == 404
    assert zed.get(f"/api/cases/{case['id']}/report.pdf").status_code == 404
    assert zed.get("/api/cases").get_json()["cases"] == []
    assert AuditEvent.query.filter_by(event_type="authz.denied", reason_code="NOT_CASE_INVESTIGATOR").count() == 3


def test_event_association_and_timeline_order(api):
    _, _, _, consent, _ = scenario(api)
    inv = investigator(api)
    case = new_case(inv)
    ids = link_access_events(inv, case["id"], consent["id"])
    # Linking again is idempotent.
    again = inv.post(f"/api/cases/{case['id']}/events", {"event_ids": ids})
    assert again.get_json()["linked"] == []
    timeline = inv.get(f"/api/cases/{case['id']}/timeline").get_json()["timeline"]
    stamps = [t["timestamp"] for t in timeline]
    assert stamps == sorted(stamps)
    sources = {t["source"] for t in timeline}
    assert sources == {"audit_event", "consent_history"}
    history = [t["version"]["change_type"] for t in timeline if t["source"] == "consent_history"]
    assert history == ["created", "withdrawn"]


def test_link_rejects_unknown_events(api):
    inv = investigator(api)
    case = new_case(inv)
    resp = inv.post(f"/api/cases/{case['id']}/events", {"event_ids": ["00000000-0000-0000-0000-000000000000"]})
    assert resp.status_code == 400


def test_timeline_filters(api):
    _, _, _, consent, _ = scenario(api)
    inv = investigator(api)
    case = new_case(inv)
    link_access_events(inv, case["id"], consent["id"])
    denied = inv.get(f"/api/cases/{case['id']}/timeline?outcome=denied").get_json()["timeline"]
    events = [t for t in denied if t["source"] == "audit_event"]
    assert len(events) == 3 and all(t["event"]["reason_code"] == "DENY_CONSENT_WITHDRAWN" for t in events)
    by_actor = inv.get(f"/api/cases/{case['id']}/timeline?actor_id=2&action=read").get_json()["timeline"]
    assert all(t["event"]["actor_id"] == 2 for t in by_actor if t["source"] == "audit_event")


def test_case_indicators_from_linked_events(api):
    _, _, _, consent, _ = scenario(api)
    inv = investigator(api)
    case = new_case(inv)
    link_access_events(inv, case["id"], consent["id"])
    body = inv.get(f"/api/cases/{case['id']}/indicators").get_json()
    codes = {i["rule_code"] for i in body["indicators"]}
    assert codes == {"ACCESS_AFTER_WITHDRAWAL", "REPEATED_DENIALS"}
    withdrawal = next(i for i in body["indicators"] if i["rule_code"] == "ACCESS_AFTER_WITHDRAWAL")
    real_ids = {e.event_id for e in AuditEvent.query.filter_by(reason_code="DENY_CONSENT_WITHDRAWN")}
    assert set(withdrawal["event_ids"]) == real_ids
    # Thresholds are configurable per request and validated.
    strict = inv.get(f"/api/cases/{case['id']}/indicators?denial_threshold=4").get_json()
    assert "REPEATED_DENIALS" not in {i["rule_code"] for i in strict["indicators"]}
    assert inv.get(f"/api/cases/{case['id']}/indicators?denial_threshold=0").status_code == 400


def test_global_detection_endpoint(api):
    scenario(api)
    inv = investigator(api)
    body = inv.get("/api/detection/indicators").get_json()
    assert "ACCESS_AFTER_WITHDRAWAL" in {i["rule_code"] for i in body["indicators"]}
    assert body["events_examined"] > 0


def test_notes_and_status_changes(api):
    inv = investigator(api)
    case = new_case(inv)
    cid = case["id"]
    assert inv.post(f"/api/cases/{cid}/notes", {"note_type": "finding", "content": "Access after withdrawal confirmed."}).status_code == 201
    assert inv.post(f"/api/cases/{cid}/notes", {"note_type": "opinion", "content": "x"}).status_code == 400
    assert inv.patch(f"/api/cases/{cid}", {"status": "under_review"}).get_json()["case"]["status"] == "under_review"
    closed = inv.patch(f"/api/cases/{cid}", {"status": "closed"}).get_json()["case"]
    assert closed["status"] == "closed" and closed["closed_at"]
    # Re-opening needs a justification; closed -> open directly is not allowed.
    assert inv.patch(f"/api/cases/{cid}", {"status": "open"}).status_code == 409
    assert inv.patch(f"/api/cases/{cid}", {"status": "under_review"}).status_code == 400
    reopened = inv.patch(f"/api/cases/{cid}", {"status": "under_review", "status_note": "New evidence"}).get_json()
    assert reopened["case"]["status"] == "under_review"
    assert any("New evidence" in n["content"] for n in reopened["notes"])
    types = [e.event_type for e in AuditEvent.query.filter_by(resource_type="case").all()]
    assert types.count("case.updated") == 3 and "case.note_added" in types


def test_report_pdf_content_and_authorization(api):
    alice, acme, _, consent, _ = scenario(api)
    inv = investigator(api)
    case = new_case(inv)
    ids = link_access_events(inv, case["id"], consent["id"])
    inv.post(f"/api/cases/{case['id']}/notes", {"note_type": "conclusion", "content": "Synthetic conclusion text."})

    for client in (alice, acme):
        assert client.get(f"/api/cases/{case['id']}/report.pdf").status_code == 403

    resp = inv.get(f"/api/cases/{case['id']}/report.pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert "attachment" in resp.headers["Content-Disposition"]
    assert resp.data.startswith(b"%PDF-")
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(resp.data)).pages)
    flat = text.replace("\n", "")
    assert "ConsentGuard" in text and "Investigation Report" in text
    assert case["case_number"] in text
    assert "ACCESS_AFTER_WITHDRAWAL" in text
    assert "Synthetic conclusion text." in text
    assert "VALID" in text
    for event_id in ids:
        assert event_id in flat, event_id
    assert "5.1 mmol" not in text  # no plaintext protected data
    assert AuditEvent.query.filter_by(event_type="case.report_generated").count() == 1


def test_report_is_deterministic_for_same_inputs(api):
    from app.investigations import cases as svc
    from app.models import InvestigationCase
    from app.reports.pdf import build_case_report
    from app.services import audit

    _, _, _, consent, _ = scenario(api)
    inv = investigator(api)
    case = new_case(inv)
    link_access_events(inv, case["id"], consent["id"])
    obj = db.session.get(InvestigationCase, case["id"])
    events = svc.linked_events(obj)
    indicators, th = svc.case_indicators(obj)
    integrity = audit.verify_chain()
    integrity["checked_at"] = "2026-01-01T00:00:00.000000Z"
    kwargs = dict(case=obj, events=events, consents=svc.related_consents(events), indicators=indicators,
                  thresholds=th.as_dict(), integrity=integrity, notes=obj.notes, people=svc.people_for(events, obj),
                  generated_at="2026-01-01T00:00:00.000000Z", generated_by=obj.investigator_id)
    assert build_case_report(**kwargs) == build_case_report(**kwargs)
