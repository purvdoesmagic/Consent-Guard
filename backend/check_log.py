"""Check the activity log from the terminal (same check as the "Check the log" button).

Run from the backend folder:  python check_log.py
Add --last 10 to also print the last 10 entries with their hashes.
"""

import sys

from app import create_app
from audit_log import verify_chain
from models import LogEntry

app = create_app()
with app.app_context():
    result = verify_chain()
    print(f"Entries checked: {result['count']}")
    print(f"Last hash:       {result['last_hash']}")
    for problem in result["problems"]:
        print(f"  Entry {problem['id']}: {problem['problem']}")
    print("Result:          " + ("VALID (no changes found)" if result["valid"] else "INVALID (the log was changed)"))

    if "--last" in sys.argv:
        count = int(sys.argv[sys.argv.index("--last") + 1])
        print(f"\nLast {count} entries (each prev_hash = hash of the entry before it):")
        for e in LogEntry.query.order_by(LogEntry.id.desc()).limit(count).all()[::-1]:
            print(f"  #{e.id:<3} {e.action:<16} {e.result:<8} prev={e.prev_hash[:10]}...  hash={e.hash[:10]}...")
