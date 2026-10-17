"""Forensic case study CG-2026-0001: access after consent withdrawal, then an insider log cover-up.

Runs on its OWN database (backend/instance/case_study.db); the demo database is never touched.
All people and data are synthetic. Full walkthrough: docs/case-study.md.

    backend\\.venv\\Scripts\\python.exe scripts\\case_study.py setup [--reset]   # stage the incident + open the case
    backend\\.venv\\Scripts\\python.exe scripts\\case_study.py app-verify        # the application's own chain check
    backend\\.venv\\Scripts\\python.exe scripts\\case_study.py cover-up          # insider deletes evidence, re-hashes chain

To browse the case in the UI, start the backend against this database:

    cd backend
    $env:CG_DATABASE_URL = "sqlite:///instance/case_study.db"; .\\.venv\\Scripts\\python.exe wsgi.py
"""

import os
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
DB = ROOT / "backend" / "instance" / "case_study.db"

from app.services.audit import GENESIS_HASH, hash_fields  # noqa: E402  (needs sys.path above)

INSIDER_TARGET = "quickloans"


def make_app():
    from app import create_app

    os.environ["CG_DATABASE_URL"] = "sqlite:///instance/case_study.db"
    return create_app({"RATELIMIT_ENABLED": False})


def setup(reset):
    import pyotp
    from flask_migrate import upgrade

    from app.cli import DEMO_PASSWORD, _DemoClient
    from app.extensions import limiter
    from app.models import User
    from app.services.users import create_user
    from app.utils.time import to_iso, utcnow

    if DB.exists():
        if not reset:
            sys.exit(f"{DB} already exists. Use 'setup --reset' to recreate it.")
        DB.unlink()
    app = make_app()
    with app.app_context():
        upgrade()
        limiter.enabled = False
        clients = {}
        for username, display, role in [("carol", "Carol Synthetic", "subject"), ("dave", "Dave Synthetic", "subject"),
                                        ("quickloans", "QuickLoans Credit Ltd", "processor")]:
            c = _DemoClient(app)
            c.call("post", "/api/auth/register",
                   {"username": username, "display_name": display, "role": role, "password": DEMO_PASSWORD})
            c.call("post", "/api/auth/login", {"username": username, "password": DEMO_PASSWORD})
            clients[username] = c
        create_user("ivy", DEMO_PASSWORD, "Ivy Investigator", "investigator")
        ivy = _DemoClient(app)
        ivy.call("post", "/api/auth/login", {"username": "ivy", "password": DEMO_PASSWORD})
        secret = ivy.call("post", "/api/auth/mfa/setup")["secret"]
        ivy.call("post", "/api/auth/mfa/enable", {"code": pyotp.TOTP(secret).now()})
        ids = {u.username: u.id for u in User.query.all()}
        carol, dave, ql = clients["carol"], clients["dave"], clients["quickloans"]

        def record(client, label, category, fields):
            fields["Notice"] = "SYNTHETIC DEMO DATA"
            return client.call("post", "/api/records",
                               {"label": label, "category": category, "fields": fields})["record"]["id"]

        def access(record_id, purpose):
            ql.call("post", f"/api/records/{record_id}/access", {"action": "read", "purpose": purpose}, expect=None)

        c_fin = record(carol, "Synthetic credit file", "financial", {"Score band": "Good (fictional)"})
        c_contact = record(carol, "Synthetic contact card", "contact", {"Phone": "+00 000 0001"})
        c_loc = record(carol, "Synthetic location history", "location", {"City": "Sampletown"})
        d_recs = [record(dave, "Synthetic credit file", "financial", {"Score band": "Fair (fictional)"}),
                  record(dave, "Synthetic contact card", "contact", {"Email": "dave@example.invalid"}),
                  record(dave, "Synthetic vaccination record", "health", {"Vaccine": "Fictional-Vax"})]

        # Phase 1 - legitimate processing under consent
        consent = carol.call("post", "/api/consents", {
            "recipient_id": ids["quickloans"], "purpose": "service_delivery", "categories": ["financial", "contact"],
            "expires_at": to_iso(utcnow() + timedelta(days=180))})["consent"]["id"]
        access(c_fin, "service_delivery")        # ALLOW_CONSENT
        access(c_contact, "service_delivery")    # ALLOW_CONSENT
        # Phase 2 - function creep before withdrawal
        access(c_contact, "marketing")           # DENY_PURPOSE_NOT_COVERED   (R4)
        access(c_loc, "service_delivery")        # DENY_CATEGORY_NOT_COVERED  (R5)
        # Phase 3 - Carol withdraws; QuickLoans keeps trying
        carol.call("post", f"/api/consents/{consent}/withdraw")
        for rec in (c_contact, c_contact, c_contact, c_fin):
            access(rec, "service_delivery")      # DENY_CONSENT_WITHDRAWN     (R2, and R1 overall)
        # Phase 4 - probing other customers' records
        for rec in d_recs:
            access(rec, "marketing")             # DENY_NO_CONSENT            (R6)

        # Phase 5 - complaint received; investigator opens the case and preserves the evidence
        case = ivy.call("post", "/api/cases", {
            "title": "Complaint: marketing contact after consent withdrawal (QuickLoans)",
            "description": "Data subject carol reports marketing calls from QuickLoans Credit Ltd after she withdrew "
                           "consent. Determine whether QuickLoans accessed or attempted to access her data after "
                           "withdrawal, and whether other subjects are affected. Synthetic case study."})["case"]
        evts = ivy.call("get", f"/api/audit/events?actor_id={ids['quickloans']}&event_type=record.access&page_size=200")
        cons = ivy.call("get", f"/api/audit/events?consent_id={consent}&event_type=consent.&page_size=50")
        ivy.call("post", f"/api/cases/{case['id']}/events", {
            "event_ids": [e["event_id"] for e in evts["events"] + cons["events"]],
            "rationale": "All QuickLoans record access attempts and the lifecycle of carol's consent"})
        ivy.call("post", "/api/audit/verify")
        limiter.enabled = True

    print(f"Case-study database created: {DB}")
    print(f"  Accounts (password {DEMO_PASSWORD}): carol, dave (subjects), quickloans (processor), ivy (investigator)")
    print(f"  ivy's TOTP secret: {secret}")
    print(f"  Case {case['case_number']} opened by ivy. Next: acquire evidence E1 (see docs/case-study.md).")


def app_verify():
    from app.services import audit

    with make_app().app_context():
        result = audit.verify_chain()
    print(f"Application verify_chain(): {'VALID' if result['valid'] else 'INVALID'} - {result['event_count']} events, "
          f"head seq {result['head_seq']} {result['head_hash']}")
    for f in result["findings"]:
        print(f"  {f['type']} seq {f['seq']}: {f['message']}")
    return 0 if result["valid"] else 1


def cover_up(db_path, username=INSIDER_TARGET):
    """Anti-forensics by an insider with database access and knowledge of the algorithm.

    Deletes every denied access attempt by ``username`` (and its case links),
    then renumbers and re-hashes the rest of the chain and rewrites the stored
    checkpoints so that the application's own verification reports VALID.
    Returns the deleted event IDs.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        actor = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()["id"]
        victims = conn.execute("SELECT id, event_id FROM audit_events WHERE actor_id=? AND event_type='record.access' "
                               "AND outcome='denied'", (actor,)).fetchall()
        for v in victims:
            conn.execute("DELETE FROM case_events WHERE audit_event_id=?", (v["id"],))
            conn.execute("DELETE FROM audit_events WHERE id=?", (v["id"],))

        remap, prev = {}, GENESIS_HASH
        for new_seq, row in enumerate(conn.execute("SELECT * FROM audit_events ORDER BY seq").fetchall(), start=1):
            fields = dict(row, seq=new_seq, prev_hash=prev)
            _, digest = hash_fields(fields)
            conn.execute("UPDATE audit_events SET seq=?, prev_hash=?, hash=? WHERE id=?",
                         (new_seq, prev, digest, row["id"]))
            remap[row["hash"]] = (new_seq, digest)
            prev = digest
        for cp in conn.execute("SELECT id, head_hash FROM audit_checkpoints").fetchall():
            if cp["head_hash"] in remap:
                seq, digest = remap[cp["head_hash"]]
                conn.execute("UPDATE audit_checkpoints SET head_seq=?, head_hash=? WHERE id=?", (seq, digest, cp["id"]))
    conn.close()
    return [v["event_id"] for v in victims]


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "setup":
        setup(reset="--reset" in sys.argv)
    elif command == "app-verify":
        sys.exit(app_verify())
    elif command == "cover-up":
        if not DB.exists():
            sys.exit("Run 'setup' first.")
        deleted = cover_up(DB)
        print(f"Insider removed {len(deleted)} audit events by {INSIDER_TARGET}, re-hashed the chain and "
              "rewrote the checkpoints.")
        print("Now run 'app-verify': the application's own check will report VALID.")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
