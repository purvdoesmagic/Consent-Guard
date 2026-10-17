import re

from flask import Blueprint, g

from app.constants import DATA_CATEGORIES, PURPOSES, RECORD_ACTIONS
from app.models import Consent, ProtectedRecord
from app.security.sessions import roles_required
from app.services.records import access_record, create_record
from app.utils.errors import ApiError
from app.utils.validation import get_choice, get_str, invalid, json_body

bp = Blueprint("records", __name__, url_prefix="/api/records")

MAX_FIELDS = 12
FIELD_NAME = r"[A-Za-z][A-Za-z0-9 _-]{0,39}"


@bp.get("")
@roles_required("subject", "processor")
def list_records():
    """Metadata only (never ciphertext or plaintext).

    Subjects see their own records. Processors see records belonging to
    subjects who have granted them at least one consent (any status), so a
    processor can still attempt access after withdrawal - and be denied and
    logged - without being able to enumerate unrelated subjects' records.
    """
    user = g.user
    if user.role == "subject":
        records = ProtectedRecord.query.filter_by(owner_id=user.id).order_by(ProtectedRecord.created_at.desc()).all()
    else:
        owner_ids = {c.subject_id for c in Consent.query.filter_by(recipient_id=user.id).all()}
        records = (
            ProtectedRecord.query.filter(ProtectedRecord.owner_id.in_(owner_ids))
            .order_by(ProtectedRecord.created_at.desc()).all() if owner_ids else []
        )
    return {"records": [r.to_metadata() for r in records]}


@bp.post("")
@roles_required("subject")
def create():
    data = json_body()
    category = get_choice(data, "category", set(DATA_CATEGORIES))
    label = get_str(data, "label", min_len=3, max_len=120)
    fields = data.get("fields")
    if not isinstance(fields, dict) or not 1 <= len(fields) <= MAX_FIELDS:
        raise invalid("fields", f"'fields' must be an object with 1-{MAX_FIELDS} entries.")
    clean = {}
    for name, value in fields.items():
        if not isinstance(name, str) or not re.fullmatch(FIELD_NAME, name):
            raise invalid("fields", "Field names must start with a letter and be at most 40 characters.")
        if not isinstance(value, str) or len(value) > 500:
            raise invalid("fields", "Field values must be strings of at most 500 characters.")
        clean[name] = value
    record = create_record(g.user, category, label, clean)
    return {"record": record.to_metadata()}, 201


@bp.post("/<record_id>/access")
@roles_required("subject", "processor", "investigator")
def access(record_id):
    """Request access to a record. Investigators are routed through the same
    decision so their (denied) attempts are evaluated and logged too."""
    data = json_body()
    action = get_choice(data, "action", RECORD_ACTIONS)
    purpose = data.get("purpose")
    if purpose is not None and purpose not in PURPOSES:
        raise invalid("purpose", "Unknown purpose.")
    decision, payload, outcome = access_record(g.user, record_id, action, purpose)
    if outcome == "failure":
        raise ApiError(500, "DECRYPTION_FAILED", "The record could not be decrypted. The event has been logged.")
    if not decision.allowed:
        raise ApiError(403, decision.public_reason, "Access denied.", {"reason": decision.public_reason})
    return {"record_id": record_id, "decision": decision.reason, "consent_id": decision.consent_id,
            "action": action, "payload": payload}
