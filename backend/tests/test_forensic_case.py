"""Case study tooling: independent examiner (scripts/forensic_examiner.py) and
the insider cover-up (scripts/case_study.py) on an isolated test database."""

import importlib.util
import json
import os
import sqlite3
import stat
from pathlib import Path

import pytest

from app.extensions import db
from app.models import User
from app.services import audit
from tests.conftest import enable_mfa, make_user

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


examiner = _load("forensic_examiner")
case_study = _load("case_study")


@pytest.fixture
def incident(app, api):
    """A processor with allowed and denied accesses, a case linking them, and a checkpoint."""
    alice, proc = make_user(api, "alice"), make_user(api, "quickloans", "processor")
    rec = alice.post("/api/records", {"label": "Synthetic contact card", "category": "contact",
                                      "fields": {"Phone": "+00 000 0001"}}).get_json()
    rec_id = rec["record"]["id"]
    pid = User.query.filter_by(username="quickloans").one().id
    cid = alice.post("/api/consents", {"recipient_id": pid, "purpose": "service_delivery",
                                       "categories": ["contact"]}).get_json()["consent"]["id"]
    proc.post(f"/api/records/{rec_id}/access", {"action": "read", "purpose": "service_delivery"})
    alice.post(f"/api/consents/{cid}/withdraw")
    for _ in range(3):
        proc.post(f"/api/records/{rec_id}/access", {"action": "read", "purpose": "service_delivery"})
    ivy = make_user(api, "ivy", "investigator")
    enable_mfa(ivy)
    case = ivy.post("/api/cases", {"title": "Access after withdrawal", "description": "Test case"}).get_json()["case"]
    ids = [e["event_id"] for e in ivy.get(f"/api/audit/events?actor_id={pid}&page_size=50").get_json()["events"]]
    assert ivy.post(f"/api/cases/{case['id']}/events", {"event_ids": ids, "rationale": "evidence"}).status_code == 200
    ivy.post("/api/audit/verify")
    db.session.remove()
    return Path(app.config["SQLALCHEMY_DATABASE_URI"][len("sqlite:///"):])


def _acquire(db_path, out):
    examiner.main(["acquire", "--db", str(db_path), "--out", str(out), "--examiner", "test"])
    return json.loads((out / "manifest.json").read_text())


def test_examiner_agrees_with_application_and_protects_evidence(incident, tmp_path):
    manifest = _acquire(incident, tmp_path / "E1")
    app_result = audit.verify_chain()
    assert manifest["anchor"]["head_hash"] == app_result["head_hash"]
    assert manifest["source_sha256"] == manifest["image_sha256"]
    assert examiner.main(["verify", str(tmp_path / "E1"), "--examiner", "test"]) == 0
    custody = json.loads((tmp_path / "E1" / "manifest.json").read_text())["custody"]
    assert [c["action"] for c in custody] == ["acquired", "verified"]
    with pytest.raises(SystemExit):  # evidence folders are never overwritten
        _acquire(incident, tmp_path / "E1")


def test_full_chain_rewrite_passes_app_check_but_not_examiner(incident, tmp_path):
    _acquire(incident, tmp_path / "E1")
    deleted = case_study.cover_up(incident)
    assert len(deleted) == 3

    db.session.remove()
    assert audit.verify_chain()["valid"]  # documented limitation: internal check is fooled

    _acquire(incident, tmp_path / "E2")
    assert examiner.main(["verify", str(tmp_path / "E2"), "--anchor", str(tmp_path / "E1"),
                          "--examiner", "test"]) == 1
    with examiner.open_image(tmp_path / "E2" / "evidence.db") as conn:
        events = examiner.load_events(conn)
    assert {eid for _, eid in examiner.dangling_references(events)} == set(deleted)
    assert examiner.check_anchor(events, json.loads((tmp_path / "E1" / "manifest.json").read_text())["anchor"])
    assert examiner.main(["compare", str(tmp_path / "E1"), str(tmp_path / "E2"), "--examiner", "test"]) == 1


def test_carving_recovers_deleted_events_with_valid_hashes(incident, tmp_path):
    case_study.cover_up(incident)
    _acquire(incident, tmp_path / "E2")
    out = tmp_path / "carved.json"
    examiner.main(["carve", str(tmp_path / "E2"), "--out", str(out), "--examiner", "test"])
    recovered = [r for r in json.loads(out.read_text()) if r["reason_code"] == "DENY_CONSENT_WITHDRAWN"]
    assert len(recovered) == 3
    assert all(r["self_consistent"] for r in recovered)


def test_examiner_detects_modified_event_and_modified_image(incident, tmp_path):
    with sqlite3.connect(incident) as conn:
        conn.execute("UPDATE audit_events SET outcome='allowed' WHERE reason_code='DENY_CONSENT_WITHDRAWN'")
    _acquire(incident, tmp_path / "E1")
    image = tmp_path / "E1" / "evidence.db"
    with examiner.open_image(image) as conn:
        findings = examiner.verify_chain(examiner.load_events(conn))["findings"]
    assert {f[0] for f in findings} == {"HASH_MISMATCH"}

    os.chmod(image, stat.S_IWRITE | stat.S_IREAD)
    with open(image, "ab") as fh:
        fh.write(b"\0")
    assert examiner.main(["verify", str(tmp_path / "E1"), "--examiner", "test"]) == 1
