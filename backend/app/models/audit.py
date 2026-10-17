import json

from app.extensions import db


class AuditEvent(db.Model):
    """Structured, hash-chained security/access event.

    ``timestamp`` is stored as the exact canonical string used in the hash
    (``YYYY-MM-DDTHH:MM:SS.ffffffZ``), which also sorts chronologically.
    ``details_json`` is stored as canonical JSON text for the same reason.
    ``seq`` and ``prev_hash`` are unique so two writers can never both extend
    the same chain position.
    """

    __tablename__ = "audit_events"

    id = db.Column(db.Integer, primary_key=True)
    seq = db.Column(db.Integer, unique=True, nullable=False, index=True)
    event_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    timestamp = db.Column(db.String(32), nullable=False, index=True)
    event_type = db.Column(db.String(60), nullable=False, index=True)
    actor_id = db.Column(db.Integer, nullable=True, index=True)
    subject_id = db.Column(db.Integer, nullable=True, index=True)  # owner of affected data
    resource_type = db.Column(db.String(40), nullable=True)
    resource_id = db.Column(db.String(64), nullable=True, index=True)
    action = db.Column(db.String(40), nullable=True)
    outcome = db.Column(db.String(20), nullable=False)  # success|allowed|denied|failure|info
    reason_code = db.Column(db.String(60), nullable=True)
    consent_id = db.Column(db.Integer, nullable=True, index=True)
    request_id = db.Column(db.String(36), nullable=True)
    details_json = db.Column(db.Text, nullable=False, default="{}")
    prev_hash = db.Column(db.String(64), unique=True, nullable=False)
    hash = db.Column(db.String(64), unique=True, nullable=False)

    @property
    def details(self):
        try:
            return json.loads(self.details_json or "{}")
        except ValueError:
            return {"_unparseable": True}

    def to_dict(self):
        return {
            "seq": self.seq,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "actor_id": self.actor_id,
            "subject_id": self.subject_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
            "consent_id": self.consent_id,
            "request_id": self.request_id,
            "details": self.details,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


class AuditCheckpoint(db.Model):
    """Head of the chain as observed at each explicit verification run.
    Lets a later verification detect truncation of the tail, provided this
    table was not rewritten too (see docs/threat-model.md)."""

    __tablename__ = "audit_checkpoints"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.String(32), nullable=False)
    head_seq = db.Column(db.Integer, nullable=False)
    head_hash = db.Column(db.String(64), nullable=False)
    verified_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    valid = db.Column(db.Boolean, nullable=False)
    event_count = db.Column(db.Integer, nullable=False)
