"""Demonstrate audit-chain tamper detection on the LOCAL DEVELOPMENT database.

Simulates an insider with direct database access who tries to hide evidence,
bypassing the application entirely:

    python scripts\\tamper_demo.py modify    # flip the newest denied access event to "allowed"
    python scripts\\tamper_demo.py delete    # delete the newest denied access event
    python scripts\\tamper_demo.py restore   # put the original row back exactly

After `modify` or `delete`, open Integrity verification in the UI (or the
dashboard) to see the findings; then run `restore` and verify again.
The original row is saved to backend/instance/tamper_backup.json. Only one
tampering can be pending at a time.
"""

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "backend" / "instance" / "consentguard.db"
BACKUP = DB.parent / "tamper_backup.json"


def connect():
    if not DB.exists():
        sys.exit(f"Database not found at {DB}. Run 'flask --app wsgi db upgrade' and 'seed-demo' first.")
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def target_row(conn):
    row = conn.execute(
        "SELECT * FROM audit_events WHERE event_type='record.access' AND outcome='denied' ORDER BY seq DESC LIMIT 1"
    ).fetchone()
    if row is None:
        sys.exit("No denied record.access event to tamper with.")
    return row


def tamper(mode):
    if BACKUP.exists():
        sys.exit("A tampering is already pending. Run 'restore' first.")
    with connect() as conn:
        row = target_row(conn)
        BACKUP.write_text(json.dumps({"mode": mode, "row": dict(row)}, indent=2), encoding="utf-8")
        if mode == "modify":
            conn.execute("UPDATE audit_events SET outcome='allowed', reason_code='ALLOW_CONSENT' WHERE id=?",
                         (row["id"],))
            print(f"Modified event seq {row['seq']} ({row['event_id']}): denied -> allowed.")
        else:
            conn.execute("DELETE FROM case_events WHERE audit_event_id=?", (row["id"],))
            conn.execute("DELETE FROM audit_events WHERE id=?", (row["id"],))
            print(f"Deleted event seq {row['seq']} ({row['event_id']}).")
    print("Now run integrity verification in the UI. Afterwards: python scripts\\tamper_demo.py restore")


def restore():
    if not BACKUP.exists():
        sys.exit("Nothing to restore.")
    saved = json.loads(BACKUP.read_text(encoding="utf-8"))
    row = saved["row"]
    with connect() as conn:
        if saved["mode"] == "modify":
            conn.execute("UPDATE audit_events SET outcome=?, reason_code=? WHERE id=?",
                         (row["outcome"], row["reason_code"], row["id"]))
        else:
            columns = ", ".join(row)
            placeholders = ", ".join("?" for _ in row)
            conn.execute(f"INSERT INTO audit_events ({columns}) VALUES ({placeholders})", tuple(row.values()))
            print("Note: if this event was linked to a case, re-link it from the audit trail.")
    BACKUP.unlink()
    print(f"Restored event seq {row['seq']}. Verify again: the chain should be valid.")


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in {"modify", "delete", "restore"}:
        sys.exit(__doc__)
    restore() if sys.argv[1] == "restore" else tamper(sys.argv[1])


if __name__ == "__main__":
    main()
