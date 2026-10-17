from datetime import timedelta

from app.models import User
from app.utils.time import to_iso, utcnow
from tests.conftest import make_user


def setup_parties(api):
    """alice (subject) with a health record; acme (processor); bob (subject)."""
    alice = make_user(api, "alice")
    acme = make_user(api, "acme", role="processor")
    bob = make_user(api, "bob")
    acme_id = User.query.filter_by(username="acme").one().id
    record = alice.post("/api/records", {
        "label": "Synthetic blood panel", "category": "health",
        "fields": {"Glucose": "5.1 mmol/L", "Note": "SYNTHETIC DEMO DATA"},
    }).get_json()["record"]
    return alice, acme, bob, acme_id, record


def grant(subject_client, recipient_id, purpose="medical_research", categories=("health",), expires_in=None):
    body = {"recipient_id": recipient_id, "purpose": purpose, "categories": list(categories)}
    if expires_in is not None:
        body["expires_at"] = to_iso(utcnow() + expires_in)
    resp = subject_client.post("/api/consents", body)
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["consent"]


def read(client, record_id, purpose="medical_research", action="read"):
    return client.post(f"/api/records/{record_id}/access", {"action": action, "purpose": purpose})


def shift_time(monkeypatch, delta):
    """Move the clock used by consent/authorization services forward."""
    future = utcnow() + delta
    for target in ("app.services.consent.utcnow", "app.services.authorization.utcnow",
                   "app.services.dashboard.utcnow", "app.security.sessions.utcnow"):
        monkeypatch.setattr(target, lambda: future)
    return future


__all__ = ["setup_parties", "grant", "read", "shift_time", "timedelta"]
