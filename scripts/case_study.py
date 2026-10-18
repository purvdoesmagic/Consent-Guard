"""Case study: did QuickLoans misuse Carol's data, and did someone hide it?

Story (all data is fake):
  1. Carol lets QuickLoans use her financial and contact data for her loan (purpose "service").
  2. QuickLoans also tries to use her phone number for marketing and to see her location -> blocked.
  3. Carol withdraws permission. QuickLoans keeps trying (4 times) and also tries
     Dave's records (3 times), who never gave permission -> all blocked.
  4. An investigator opens a case and saves a copy of the database as evidence.
  5. Someone with database access deletes QuickLoans' blocked attempts and
     recalculates all hashes, so the app's own check still says VALID.
  6. Comparing with the saved copy proves the cover-up and shows what was deleted.

Run from the project root, in this order (uses its own database, case_study.db):
  backend\\.venv\\Scripts\\python.exe scripts\\case_study.py setup
  backend\\.venv\\Scripts\\python.exe scripts\\case_study.py save-copy
  backend\\.venv\\Scripts\\python.exe scripts\\case_study.py cover-up
  backend\\.venv\\Scripts\\python.exe scripts\\case_study.py check
"""

import hashlib
import json
import os
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app import create_app  # noqa: E402
from audit_log import FIRST_HASH, make_hash, verify_chain  # noqa: E402
from models import LogEntry, Record, User, case_logs, db  # noqa: E402
from permissions import view_record  # noqa: E402
from seed import give_consent, make_record, make_user, open_case, withdraw  # noqa: E402

EVIDENCE = os.path.join(ROOT, "evidence")
COPY_DB = os.path.join(EVIDENCE, "copy-1.db")
COPY_INFO = os.path.join(EVIDENCE, "copy-1.json")


def get_app():
    return create_app({"SQLALCHEMY_DATABASE_URI": "sqlite:///case_study.db"})


def db_path(app):
    return os.path.join(app.instance_path, "case_study.db")


def file_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def setup(app):
    db.drop_all()
    db.create_all()
    carol = make_user("carol", "Carol Customer", "user")
    dave = make_user("dave", "Dave Other", "user")
    ql = make_user("quickloans", "QuickLoans Credit Ltd", "company")
    ivy = make_user("ivy", "Ivy Investigator", "investigator")

    credit = make_record(carol, "Credit file", "financial", "Credit score 712 (FAKE DATA)")
    phone = make_record(carol, "Contact details", "contact", "Phone +00 111 2222 (FAKE DATA)")
    location = make_record(carol, "Location history", "location", "Testville (FAKE DATA)")
    dave_records = [
        make_record(dave, "Credit file", "financial", "Credit score 650 (FAKE DATA)"),
        make_record(dave, "Contact details", "contact", "dave@example.invalid (FAKE DATA)"),
        make_record(dave, "Health record", "health", "Allergy: none (FAKE DATA)"),
    ]

    consent = give_consent(carol, ql, "service", ["financial", "contact"])
    view_record(ql, credit, "service")      # allowed: needed for the loan
    view_record(ql, phone, "service")       # allowed: QuickLoans now has her number
    view_record(ql, phone, "marketing")     # blocked: wrong purpose
    view_record(ql, location, "service")    # blocked: location was never allowed
    withdraw(consent)
    for record in (phone, credit, phone, credit):
        view_record(ql, record, "service")  # blocked: after withdrawal
    for record in dave_records:
        view_record(ql, record, "marketing")  # blocked: Dave never gave permission

    entries = LogEntry.query.filter_by(user_id=ql.id, action="record.view").all()
    open_case(ivy, "Carol's complaint against QuickLoans",
              "Carol withdrew permission but kept getting marketing calls from QuickLoans.", entries)
    print(f"Case set up: {LogEntry.query.count()} log entries. Log check: "
          f"{'VALID' if verify_chain()['valid'] else 'INVALID'}")


def save_copy(app):
    """Step 4: the investigator saves a copy of the database before anything else happens."""
    os.makedirs(EVIDENCE, exist_ok=True)
    shutil.copyfile(db_path(app), COPY_DB)
    last = LogEntry.query.order_by(LogEntry.id.desc()).first()
    info = {"entries": LogEntry.query.count(), "last_id": last.id, "last_hash": last.hash,
            "file_sha256": file_sha256(COPY_DB)}
    with open(COPY_INFO, "w") as f:
        json.dump(info, f, indent=2)
    print(f"Saved evidence copy: {info['entries']} entries, last hash {info['last_hash'][:16]}...")
    print("Keep this last hash somewhere safe (it is also printed in the PDF report).")


def cover_up(app):
    """Step 5: an insider edits the database directly and hides QuickLoans' blocked attempts."""
    ql = User.query.filter_by(username="quickloans").first()
    entries = LogEntry.query.order_by(LogEntry.id).all()
    kept = [e for e in entries if not (e.user_id == ql.id and e.result == "denied")]
    removed = len(entries) - len(kept)

    fields = ["time", "user_id", "owner_id", "action", "target", "result", "reason", "details"]
    kept_data = [(e.id, {f: getattr(e, f) for f in fields}) for e in kept]
    links = db.session.execute(case_logs.select()).all()

    # Delete everything and write the remaining entries back with new numbers and new hashes
    db.session.execute(case_logs.delete())
    LogEntry.query.delete()
    db.session.commit()

    new_ids = {}
    prev = FIRST_HASH
    for new_id, (old_id, data) in enumerate(kept_data, start=1):
        entry = LogEntry(id=new_id, prev_hash=prev, **data)
        entry.hash = make_hash(entry)
        db.session.add(entry)
        new_ids[old_id] = new_id
        prev = entry.hash
    for case_id, log_id in links:
        if log_id in new_ids:
            db.session.execute(case_logs.insert().values(case_id=case_id, log_id=new_ids[log_id]))
    db.session.commit()
    print(f"Insider deleted {removed} entries and recalculated every hash. {len(kept)} entries left.")


def check(app):
    """Step 6: check the log in two ways."""
    result = verify_chain()
    print("1) The app's own check:", "VALID" if result["valid"] else "INVALID", f"({result['count']} entries)")
    if result["valid"]:
        print("   -> The app was fooled, because every hash was recalculated.")

    if not os.path.exists(COPY_INFO):
        print("No saved copy found. Run 'save-copy' before 'cover-up'.")
        return
    with open(COPY_INFO) as f:
        info = json.load(f)

    print("2) Compare with the saved copy:")
    same_file = file_sha256(COPY_DB) == info["file_sha256"]
    print("   Saved copy unchanged since it was saved:", "YES" if same_file else "NO")

    last = db.session.get(LogEntry, info["last_id"])
    if last is None or last.hash != info["last_hash"]:
        print(f"   FAIL: the copy had {info['entries']} entries ending with hash {info['last_hash'][:16]}...,")
        print(f"         but now there are {result['count']} entries and that hash no longer exists.")
    else:
        print("   OK: the saved last hash still exists.")

    # Find entries that are in the saved copy but not in the current log
    columns = "time, user_id, action, target, result, reason"
    old_db = sqlite3.connect(f"file:{COPY_DB}?mode=ro", uri=True)
    old_rows = old_db.execute(f"SELECT {columns} FROM log_entry ORDER BY id").fetchall()
    old_db.close()
    current = {tuple(r) for r in db.session.execute(db.text(f"SELECT {columns} FROM log_entry")).all()}
    missing = [r for r in old_rows if tuple(r) not in current]

    names = {u.id: u.username for u in User.query.all()}
    records = {f"record {r.id}": f"{names[r.owner_id]}'s {r.category}" for r in Record.query.all()}
    print(f"   Entries missing compared to the copy: {len(missing)}")
    for time, user_id, action, target, outcome, reason in missing:
        print(f"     {time[11:19]}  {names.get(user_id)} {action} {records.get(target, target)}: {outcome} ({reason})")

    if missing:
        print("\nResult: QuickLoans got no data after Carol withdrew permission (all those attempts were blocked),")
        print("but someone deleted exactly those blocked attempts from the log. The saved copy proves it.")


COMMANDS = {"setup": setup, "save-copy": save_copy, "cover-up": cover_up, "check": check}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit("usage: python scripts/case_study.py setup | save-copy | cover-up | check")
    application = get_app()
    with application.app_context():
        COMMANDS[sys.argv[1]](application)
