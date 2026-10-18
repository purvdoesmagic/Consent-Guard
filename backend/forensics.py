"""Digital forensics tools for the investigator.

The hash chain (audit_log.py) catches small edits, but someone with direct
database access who knows the method can delete entries AND recalculate every
hash. Then the app's own check still says VALID.

The defence is to keep evidence OUTSIDE the live database:
  save_copy()  - copy the whole database to the evidence folder and record its
                 SHA-256 and the last log hash (like sealing evidence in a bag)
  compare()    - compare the live log with a saved copy and list what is missing
  restore()    - put a saved copy back (used to undo the demo cover-up)

simulate_cover_up() is for the DEMO ONLY: it plays the insider who secretly
deletes a company's blocked attempts and recalculates the hashes.
"""

import hashlib
import json
import os
import sqlite3

from flask import current_app

from audit_log import FIRST_HASH, make_hash
from models import LogEntry, User, case_logs, db, now

LOG_COLUMNS = "time, user_id, action, target, result, reason, details"


def evidence_folder():
    folder = os.path.join(current_app.instance_path, "evidence")
    os.makedirs(folder, exist_ok=True)
    return folder


def live_database_path():
    return db.engine.url.database


def file_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _copy_sqlite(source_path, target_path):
    """Copy a SQLite database safely (even while the app is using it)."""
    source = sqlite3.connect(source_path)
    target = sqlite3.connect(target_path)
    source.backup(target)
    target.close()
    source.close()


def list_copies():
    folder = evidence_folder()
    copies = []
    for name in sorted(os.listdir(folder)):
        if name.endswith(".json"):
            with open(os.path.join(folder, name)) as f:
                copies.append(json.load(f))
    return copies


def get_copy(copy_id):
    path = os.path.join(evidence_folder(), f"copy-{copy_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def save_copy(investigator, note=""):
    db.session.commit()
    copy_id = len(list_copies()) + 1
    db_file = os.path.join(evidence_folder(), f"copy-{copy_id}.db")
    last = LogEntry.query.order_by(LogEntry.id.desc()).first()
    entries = LogEntry.query.count()

    _copy_sqlite(live_database_path(), db_file)

    info = {
        "id": copy_id,
        "saved_at": now().isoformat(timespec="seconds"),
        "saved_by": investigator.username,
        "note": note,
        "entries": entries,
        "last_id": last.id if last else 0,
        "last_hash": last.hash if last else FIRST_HASH,
        "file_sha256": file_sha256(db_file),
    }
    with open(os.path.join(evidence_folder(), f"copy-{copy_id}.json"), "w") as f:
        json.dump(info, f, indent=2)
    return info


def compare(info):
    """Compare the live log with a saved copy."""
    db_file = os.path.join(evidence_folder(), f"copy-{info['id']}.db")

    # 1. Is the saved copy itself unchanged?
    copy_unchanged = file_sha256(db_file) == info["file_sha256"]

    # 2. Does the last entry we recorded still exist with the same hash?
    last = db.session.get(LogEntry, info["last_id"])
    last_hash_found = last is not None and last.hash == info["last_hash"]

    # 3. Which entries are in the copy but not in the live log?
    old_db = sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)
    old_rows = old_db.execute(f"SELECT {LOG_COLUMNS} FROM log_entry ORDER BY id").fetchall()
    old_db.close()
    live_rows = {tuple(r) for r in db.session.execute(db.text(f"SELECT {LOG_COLUMNS} FROM log_entry")).all()}
    missing = [r for r in old_rows if tuple(r) not in live_rows]

    names = {u.id: u.username for u in User.query.all()}
    return {
        "copy": info,
        "copy_unchanged": copy_unchanged,
        "last_hash_found": last_hash_found,
        "live_entries": LogEntry.query.count(),
        "missing": [
            {"time": t, "who": names.get(u, "-"), "action": a, "target": tg, "result": r, "reason": rs, "details": d}
            for t, u, a, tg, r, rs, d in missing
        ],
        "tampered": not last_hash_found or len(missing) > 0,
    }


def restore(info):
    """Replace the live database with a saved copy."""
    db_file = os.path.join(evidence_folder(), f"copy-{info['id']}.db")
    db.session.remove()
    db.engine.dispose()
    _copy_sqlite(db_file, live_database_path())


def simulate_cover_up(company_username):
    """DEMO ONLY: act like an insider who deletes a company's blocked attempts
    directly in the database and then recalculates every hash."""
    company = User.query.filter_by(username=company_username).first()
    if company is None:
        return 0
    entries = LogEntry.query.order_by(LogEntry.id).all()
    kept = [e for e in entries if not (e.user_id == company.id and e.result == "denied")]
    removed = len(entries) - len(kept)
    if removed == 0:
        return 0

    fields = ["time", "user_id", "owner_id", "action", "target", "result", "reason", "details"]
    kept_data = [(e.id, {f: getattr(e, f) for f in fields}) for e in kept]
    links = db.session.execute(case_logs.select()).all()

    # Delete everything, then write the remaining entries back with new numbers and new hashes
    db.session.execute(case_logs.delete())
    LogEntry.query.delete()
    db.session.commit()
    db.session.expunge_all()

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
    return removed
