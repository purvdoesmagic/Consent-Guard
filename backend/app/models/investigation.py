from app.extensions import db
from app.utils.time import to_iso, utcnow


class InvestigationCase(db.Model):
    __tablename__ = "investigation_cases"

    id = db.Column(db.Integer, primary_key=True)
    case_number = db.Column(db.String(20), unique=True, nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="open")
    investigator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    scope_start = db.Column(db.DateTime, nullable=True)
    scope_end = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    closed_at = db.Column(db.DateTime, nullable=True)

    investigator = db.relationship("User")
    links = db.relationship("CaseEvent", backref="case", lazy="select", cascade="all, delete-orphan")
    notes = db.relationship(
        "CaseNote", backref="case", lazy="select", order_by="CaseNote.created_at", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "case_number": self.case_number,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "investigator": self.investigator.to_public(),
            "scope_start": to_iso(self.scope_start),
            "scope_end": to_iso(self.scope_end),
            "created_at": to_iso(self.created_at),
            "updated_at": to_iso(self.updated_at),
            "closed_at": to_iso(self.closed_at),
            "linked_event_count": len(self.links),
            "note_count": len(self.notes),
        }


class CaseEvent(db.Model):
    """Association between a case and an audit event (evidence item)."""

    __tablename__ = "case_events"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("investigation_cases.id"), nullable=False, index=True)
    audit_event_id = db.Column(db.Integer, db.ForeignKey("audit_events.id"), nullable=False)
    linked_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    linked_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    rationale = db.Column(db.String(300), nullable=True)

    event = db.relationship("AuditEvent")

    __table_args__ = (db.UniqueConstraint("case_id", "audit_event_id", name="uq_case_events_case_event"),)


class CaseNote(db.Model):
    """Append-only investigator note. ``note_type`` separates general notes,
    findings (interpretation of evidence) and conclusions."""

    __tablename__ = "case_notes"

    id = db.Column(db.Integer, primary_key=True)
    case_id = db.Column(db.Integer, db.ForeignKey("investigation_cases.id"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    note_type = db.Column(db.String(20), nullable=False, default="note")
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    author = db.relationship("User")

    def to_dict(self):
        return {
            "id": self.id,
            "note_type": self.note_type,
            "content": self.content,
            "author": self.author.to_public(),
            "created_at": to_iso(self.created_at),
        }
