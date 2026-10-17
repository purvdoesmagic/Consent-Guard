from app.extensions import db
from app.utils.time import to_iso, utcnow


class Consent(db.Model):
    """A data subject's consent allowing one recipient (processor) to use
    specific data categories for one purpose. Purpose and recipient are
    immutable; a different purpose requires a new consent."""

    __tablename__ = "consents"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    recipient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    purpose = db.Column(db.String(40), nullable=False)
    categories = db.Column(db.JSON, nullable=False)  # sorted list of category codes
    status = db.Column(db.String(20), nullable=False, default="active")
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)
    withdrawn_at = db.Column(db.DateTime, nullable=True)
    expired_at = db.Column(db.DateTime, nullable=True)

    subject = db.relationship("User", foreign_keys=[subject_id])
    recipient = db.relationship("User", foreign_keys=[recipient_id])
    versions = db.relationship(
        "ConsentVersion", backref="consent", order_by="ConsentVersion.version", lazy="select"
    )

    def to_dict(self, include_history=False):
        data = {
            "id": self.id,
            "subject": self.subject.to_public(),
            "recipient": self.recipient.to_public(),
            "purpose": self.purpose,
            "categories": list(self.categories),
            "status": self.status,
            "version": self.version,
            "created_at": to_iso(self.created_at),
            "updated_at": to_iso(self.updated_at),
            "expires_at": to_iso(self.expires_at),
            "withdrawn_at": to_iso(self.withdrawn_at),
            "expired_at": to_iso(self.expired_at),
        }
        if include_history:
            data["history"] = [v.to_dict() for v in self.versions]
        return data


class ConsentVersion(db.Model):
    """Append-only snapshot written on every consent lifecycle change."""

    __tablename__ = "consent_versions"

    id = db.Column(db.Integer, primary_key=True)
    consent_id = db.Column(db.Integer, db.ForeignKey("consents.id"), nullable=False, index=True)
    version = db.Column(db.Integer, nullable=False)
    change_type = db.Column(db.String(20), nullable=False)  # created|updated|withdrawn|expired
    status = db.Column(db.String(20), nullable=False)
    categories = db.Column(db.JSON, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    changed_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    changed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)  # None = system

    __table_args__ = (db.UniqueConstraint("consent_id", "version", name="uq_consent_versions_consent_version"),)

    def to_dict(self):
        return {
            "version": self.version,
            "change_type": self.change_type,
            "status": self.status,
            "categories": list(self.categories),
            "expires_at": to_iso(self.expires_at),
            "changed_at": to_iso(self.changed_at),
            "changed_by": self.changed_by,
        }
