from audit_log import add_log, verify_chain
from models import LogEntry, db


def make_entries(count=5):
    for i in range(count):
        add_log("test", "success", target=f"item {i}")


def test_new_log_is_valid(app):
    make_entries()
    result = verify_chain()
    assert result["valid"] and result["count"] == 5


def test_each_entry_links_to_the_previous_one(app):
    make_entries()
    entries = LogEntry.query.order_by(LogEntry.id).all()
    assert entries[0].prev_hash == "0" * 64
    for before, after in zip(entries, entries[1:]):
        assert after.prev_hash == before.hash


def test_changed_entry_is_detected(app):
    make_entries()
    entry = db.session.get(LogEntry, 3)
    entry.result = "failed"
    db.session.commit()
    result = verify_chain()
    assert not result["valid"]
    assert result["problems"][0]["id"] == 3


def test_deleted_entry_is_detected(app):
    make_entries()
    db.session.delete(db.session.get(LogEntry, 3))
    db.session.commit()
    problems = verify_chain()["problems"]
    assert any("missing" in p["problem"] for p in problems)
    assert any("broken" in p["problem"] for p in problems)
