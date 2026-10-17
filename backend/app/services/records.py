"""Protected synthetic records: encryption at rest and authorized access."""

import json

from flask import current_app

from app.extensions import db
from app.models import ProtectedRecord
from app.models.record import new_record_id
from app.security.crypto import DecryptionError, get_cipher
from app.services import audit
from app.services.authorization import evaluate_record_access


def record_aad(record_id, owner_id, category):
    return {"purpose": "protected-record", "record_id": record_id, "owner_id": owner_id, "category": category}


def create_record(owner, category, label, fields, actor_id=None, commit=True):
    record_id = new_record_id()
    plaintext = json.dumps(fields, sort_keys=True, separators=(",", ":")).encode("utf-8")
    box = get_cipher().encrypt(plaintext, record_aad(record_id, owner.id, category))
    record = ProtectedRecord(id=record_id, owner_id=owner.id, category=category, label=label,
                             key_id=box["key_id"], nonce=box["nonce"], ciphertext=box["ciphertext"])
    db.session.add(record)
    audit.stage("record.created", "success", actor_id=actor_id or owner.id, subject_id=owner.id,
                resource_type="record", resource_id=record_id, action="create",
                details={"category": category, "key_id": box["key_id"]})
    if commit:
        audit.commit()
    return record


def decrypt_record(record):
    plaintext = get_cipher().decrypt(record.key_id, record.nonce, record.ciphertext,
                                     record_aad(record.id, record.owner_id, record.category))
    return json.loads(plaintext.decode("utf-8"))


def access_record(user, record_id, action, purpose):
    """Evaluate, log and (if allowed) decrypt. Returns (decision, payload, outcome)."""
    record = db.session.get(ProtectedRecord, record_id) if isinstance(record_id, str) and len(record_id) <= 64 else None
    decision = evaluate_record_access(user, record, action, purpose)
    payload = None
    outcome = "allowed" if decision.allowed else "denied"
    reason = decision.reason
    if decision.allowed:
        try:
            payload = decrypt_record(record)
        except DecryptionError:
            # Never return partial data; record the failure for investigation.
            current_app.logger.error("Decryption failed for record %s", record.id)
            outcome, reason = "failure", "DECRYPTION_FAILED"
    audit.stage("record.access", outcome, actor_id=user.id, subject_id=record.owner_id if record else None,
                resource_type="record", resource_id=record_id, action=action, reason_code=reason,
                consent_id=decision.consent_id,
                details={"purpose": purpose, "category": record.category if record else None, "role": user.role})
    audit.commit()
    return decision, payload, outcome
