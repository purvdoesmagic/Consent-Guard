"""Simple rules that spot suspicious activity in the log.

An alert is a lead for the investigator, not proof that someone did
something wrong.

R1  Many blocked attempts   - 3 or more denied views by one company within 10 minutes
R2  After withdrawal        - a company tried to view data after the user withdrew permission
R3  Wrong reason            - a company asked for data for a purpose or category not allowed
R4  Many wrong passwords    - 5 or more failed logins on one account within 10 minutes
"""

from datetime import datetime, timedelta

WINDOW = timedelta(minutes=10)


def _time(entry):
    return datetime.fromisoformat(entry.time)


def _bursts(entries, minimum):
    """Groups of at least `minimum` entries that all fall inside one 10-minute window."""
    groups = []
    i = 0
    while i < len(entries):
        group = [e for e in entries[i:] if _time(e) - _time(entries[i]) <= WINDOW]
        if len(group) >= minimum:
            groups.append(group)
            i += len(group)
        else:
            i += 1
    return groups


def _alert(rule, title, severity, explanation, entries):
    return {
        "rule": rule,
        "title": title,
        "severity": severity,
        "explanation": explanation,
        "log_ids": [e.id for e in entries],
        "first_time": entries[0].time,
    }


def find_alerts(entries, names):
    """`entries` = log entries in order, `names` = {user_id: username} for nicer messages."""
    alerts = []
    denied = [e for e in entries if e.action == "record.view" and e.result == "denied"]

    # Group denied attempts by the company that made them
    by_company = {}
    for e in denied:
        by_company.setdefault(e.user_id, []).append(e)

    for company_id, items in by_company.items():
        name = names.get(company_id, company_id)

        for group in _bursts(items, 3):
            alerts.append(_alert("R1", "Many blocked attempts", "medium",
                                 f"{name} was blocked {len(group)} times within 10 minutes.", group))

        after = [e for e in items if e.reason == "CONSENT_WITHDRAWN"]
        if after:
            alerts.append(_alert("R2", "Tried after permission was withdrawn", "high",
                                 f"{name} tried {len(after)} time(s) to view data after the user withdrew permission.",
                                 after))

        wrong = [e for e in items if e.reason in ("WRONG_PURPOSE", "CATEGORY_NOT_ALLOWED")]
        if wrong:
            alerts.append(_alert("R3", "Asked for data for the wrong reason", "medium",
                                 f"{name} asked {len(wrong)} time(s) for data with a purpose or category "
                                 "the user did not allow.", wrong))

    # Failed logins grouped by the account they targeted
    failed = {}
    for e in entries:
        if e.action == "login" and e.result == "failed":
            failed.setdefault(e.target, []).append(e)
    for username, items in failed.items():
        for group in _bursts(items, 5):
            alerts.append(_alert("R4", "Many wrong passwords", "medium",
                                 f"{len(group)} failed logins on account '{username}' within 10 minutes.", group))

    alerts.sort(key=lambda a: (a["severity"] != "high", a["first_time"]))
    return alerts
