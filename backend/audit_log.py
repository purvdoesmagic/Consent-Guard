"""Activity log that can't be secretly changed (a hash chain).

Every entry stores:
    prev_hash = the hash of the entry before it
    hash      = SHA-256 of this entry's data + prev_hash

If someone edits or deletes an entry, the hashes stop matching and
verify_chain() reports it.

Limitation: someone with direct database access who knows this method could
recalculate every hash. That is why we keep the last hash outside the system
(it is printed in every PDF report). See scripts/case_study.py.
"""

import hashlib
import json
import threading

from models import LogEntry, db, now

FIRST_HASH = "0" * 64  # the first entry links to this
_lock = threading.Lock()  # stops two requests adding entries at the same time


def make_hash(entry):
    data = {
        "id": entry.id,
        "time": entry.time,
        "user_id": entry.user_id,
        "owner_id": entry.owner_id,
        "action": entry.action,
        "target": entry.target,
        "result": entry.result,
        "reason": entry.reason,
        "details": entry.details,
        "prev_hash": entry.prev_hash,
    }
    text = json.dumps(data, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def add_log(action, result, user_id=None, owner_id=None, target=None, reason=None, details=""):
    """Add an entry to the end of the chain and save it (also saves any other pending changes)."""
    with _lock:
        last = LogEntry.query.order_by(LogEntry.id.desc()).first()
        entry = LogEntry(
            id=last.id + 1 if last else 1,
            time=now().isoformat(timespec="microseconds"),
            user_id=user_id,
            owner_id=owner_id,
            action=action,
            target=target,
            result=result,
            reason=reason,
            details=details,
            prev_hash=last.hash if last else FIRST_HASH,
        )
        entry.hash = make_hash(entry)
        db.session.add(entry)
        db.session.commit()
    return entry


def verify_chain():
    """Check every entry and return a list of problems (empty = log is intact)."""
    entries = LogEntry.query.order_by(LogEntry.id).all()
    problems = []
    expected_id = 1
    expected_prev = FIRST_HASH

    for entry in entries:
        if entry.id != expected_id:
            problems.append({"id": entry.id, "problem": f"Entries {expected_id} to {entry.id - 1} are missing"})
        if entry.prev_hash != expected_prev:
            problems.append({"id": entry.id, "problem": "Link to the previous entry is broken"})
        if make_hash(entry) != entry.hash:
            problems.append({"id": entry.id, "problem": "Entry was changed after it was saved"})
        expected_id = entry.id + 1
        expected_prev = entry.hash

    return {
        "valid": len(problems) == 0,
        "count": len(entries),
        "last_hash": entries[-1].hash if entries else FIRST_HASH,
        "problems": problems,
    }
