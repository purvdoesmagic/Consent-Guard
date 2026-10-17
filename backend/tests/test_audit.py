"""Hash-chain integrity: valid chains, tampering scenarios and concurrency."""

import json
import threading

from sqlalchemy import text

from app.extensions import db
from app.models import AuditEvent
from app.services import audit
from tests.conftest import enable_mfa, make_user


def write_events(n):
    for i in range(n):
        audit.record("test.event", "info", details={"i": i})


def test_genesis_and_linking(app):
    write_events(3)
    events = AuditEvent.query.order_by(AuditEvent.seq).all()
    assert events[0].seq == 1 and events[0].prev_hash == audit.GENESIS_HASH
    assert events[1].prev_hash == events[0].hash and events[2].prev_hash == events[1].hash
    assert all(len(e.hash) == 64 for e in events)


def test_canonical_serialization_is_deterministic():
    a = audit.canonical_json({"b": 1, "a": {"y": 2, "x": [3, "é"]}})
    b = audit.canonical_json({"a": {"x": [3, "é"], "y": 2}, "b": 1})
    assert a == b == '{"a":{"x":[3,"\\u00e9"],"y":2},"b":1}'


def test_empty_chain_is_valid(app):
    result = audit.verify_chain()
    assert result["valid"] and result["event_count"] == 0


def test_valid_chain_verifies(app):
    write_events(5)
    result = audit.verify_chain()
    assert result["valid"] is True and result["findings"] == []
    assert result["event_count"] == 5 and result["head_seq"] == 5


def test_modified_event_detected(app):
    write_events(5)
    db.session.execute(text("UPDATE audit_events SET outcome='success' WHERE seq=3"))
    db.session.commit()
    result = audit.verify_chain()
    assert not result["valid"]
    assert [(f["type"], f["seq"]) for f in result["findings"]] == [("HASH_MISMATCH", 3)]


def test_modified_details_detected(app):
    write_events(3)
    db.session.execute(text("UPDATE audit_events SET details_json=:d WHERE seq=2"), {"d": json.dumps({"i": 99})})
    db.session.commit()
    assert {f["type"] for f in audit.verify_chain()["findings"]} == {"HASH_MISMATCH"}


def test_deleted_event_detected(app):
    write_events(5)
    db.session.execute(text("DELETE FROM audit_events WHERE seq=3"))
    db.session.commit()
    types = {(f["type"], f["seq"]) for f in audit.verify_chain()["findings"]}
    assert ("SEQUENCE_GAP", 4) in types and ("PREVIOUS_HASH_MISMATCH", 4) in types


def test_reordered_events_detected(app):
    write_events(4)
    # Swap the sequence positions of events 2 and 3.
    db.session.execute(text("UPDATE audit_events SET seq=-2 WHERE seq=2"))
    db.session.execute(text("UPDATE audit_events SET seq=2 WHERE seq=3"))
    db.session.execute(text("UPDATE audit_events SET seq=3 WHERE seq=-2"))
    db.session.commit()
    findings = audit.verify_chain()["findings"]
    assert not audit.verify_chain()["valid"]
    assert {"HASH_MISMATCH", "PREVIOUS_HASH_MISMATCH"} <= {f["type"] for f in findings}


def test_invalid_predecessor_hash_detected(app):
    write_events(3)
    db.session.execute(text("UPDATE audit_events SET prev_hash=:h WHERE seq=2"), {"h": "f" * 64})
    db.session.commit()
    types = {f["type"] for f in audit.verify_chain()["findings"]}
    assert "PREVIOUS_HASH_MISMATCH" in types and "HASH_MISMATCH" in types


def _forge(seq, prev_hash, timestamp):
    fields = dict(seq=seq, event_id=f"forged-{seq}", timestamp=timestamp, event_type="forged", actor_id=None,
                  subject_id=None, resource_type=None, resource_id=None, action=None, outcome="info",
                  reason_code=None, consent_id=None, request_id=None, details_json="{}", prev_hash=prev_hash)
    _, digest = audit.hash_fields(fields)
    return AuditEvent(**fields, hash=digest)


def test_fork_insertion_blocked_by_unique_prev_hash(app):
    import pytest
    from sqlalchemy.exc import IntegrityError

    write_events(3)
    first = AuditEvent.query.filter_by(seq=1).one()
    db.session.add(_forge(99, first.hash, first.timestamp))  # second child of event 1
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_inserted_event_detected(app):
    write_events(3)
    # Shift events 2..3 up by one and insert a self-hashed forged event at seq 2.
    db.session.execute(text("UPDATE audit_events SET seq = seq + 10 WHERE seq >= 2"))
    db.session.execute(text("UPDATE audit_events SET seq = seq - 9 WHERE seq >= 12"))
    first = AuditEvent.query.filter_by(seq=1).one()
    db.session.add(_forge(2, "e" * 64, first.timestamp))
    db.session.commit()
    findings = {(f["type"], f["seq"]) for f in audit.verify_chain()["findings"]}
    assert ("PREVIOUS_HASH_MISMATCH", 2) in findings  # forged event does not link to #1
    assert ("PREVIOUS_HASH_MISMATCH", 3) in findings  # original #2 no longer links to its predecessor
    assert ("HASH_MISMATCH", 3) in findings  # renumbering changed hashed content


def test_truncation_detected_via_checkpoint(app):
    write_events(4)
    audit.verify_and_checkpoint(actor_id=None)  # checkpoint at head seq 4, then event 5 is written
    db.session.execute(text("DELETE FROM audit_events WHERE seq >= 4"))
    db.session.commit()
    types = {f["type"] for f in audit.verify_chain()["findings"]}
    assert "CHECKPOINT_MISMATCH" in types


def test_tail_truncation_without_checkpoint_is_not_detectable(app):
    """Documented limitation: removing the newest events leaves a valid prefix."""
    write_events(4)
    db.session.execute(text("DELETE FROM audit_events WHERE seq = 4"))
    db.session.commit()
    assert audit.verify_chain()["valid"] is True


def test_sensitive_detail_keys_rejected(app):
    import pytest

    with pytest.raises(ValueError):
        audit.stage("test", "info", details={"password": "x"})


def test_failed_transaction_writes_no_events(app):
    audit.stage("test.event", "info")
    db.session.rollback()
    audit.discard()
    write_events(1)
    assert AuditEvent.query.count() == 1 and audit.verify_chain()["valid"]


def test_concurrent_writers_keep_chain_valid(app):
    errors = []

    def worker():
        with app.app_context():
            try:
                for i in range(15):
                    audit.record("test.concurrent", "info", details={"i": i})
            except Exception as exc:  # pragma: no cover - reported below
                errors.append(repr(exc))
            finally:
                db.session.remove()

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    result = audit.verify_chain()
    assert result["event_count"] == 90
    assert result["valid"], result["findings"]


def test_audit_event_visibility_is_scoped(api):
    from tests.helpers import grant, read, setup_parties

    alice, acme, bob, acme_id, record = setup_parties(api)
    grant(alice, acme_id)
    read(acme, record["id"])
    bob_events = bob.get("/api/audit/events?page_size=200").get_json()["events"]
    assert all(e["actor_id"] == 3 or e["subject_id"] == 3 for e in bob_events)
    alice_types = {e["event_type"] for e in alice.get("/api/audit/events?page_size=200").get_json()["events"]}
    assert "record.access" in alice_types  # alice sees access to her data
    acme_events = acme.get("/api/audit/events?page_size=200").get_json()["events"]
    assert all(e["actor_id"] == 2 for e in acme_events)


def test_audit_filters(api):
    from tests.helpers import grant, read, setup_parties

    alice, acme, _, acme_id, record = setup_parties(api)
    consent = grant(alice, acme_id)
    read(acme, record["id"])
    read(acme, record["id"], purpose="marketing")
    denied = alice.get("/api/audit/events?outcome=denied").get_json()
    assert denied["total"] == 1 and denied["events"][0]["reason_code"] == "DENY_PURPOSE_NOT_COVERED"
    by_consent = alice.get(f"/api/audit/events?consent_id={consent['id']}&event_type=consent.").get_json()
    assert {e["event_type"] for e in by_consent["events"]} == {"consent.created"}
    assert alice.get("/api/audit/events?outcome=bogus").status_code == 400
    assert alice.get("/api/audit/events?start=2030-01-01T00:00:00Z&end=2020-01-01T00:00:00Z").status_code == 400


def test_verify_endpoint_requires_investigator_with_mfa(api):
    alice = make_user(api, "alice")
    assert alice.post("/api/audit/verify").status_code == 403
    inv = make_user(api, "ivy", role="investigator")
    resp = inv.post("/api/audit/verify")
    assert resp.status_code == 403 and resp.get_json()["error"]["code"] == "MFA_ENROLLMENT_REQUIRED"
    enable_mfa(inv)
    resp = inv.post("/api/audit/verify")
    assert resp.status_code == 200 and resp.get_json()["valid"] is True
    status = alice.get("/api/audit/integrity").get_json()
    assert status["valid"] is True and "findings" not in status
