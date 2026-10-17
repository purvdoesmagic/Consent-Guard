import uuid

from app.extensions import db
from app.utils.time import to_iso, utcnow


def new_record_id():
    return uuid.uuid4().hex


class ProtectedRecord(db.Model):
    """Synthetic protected record. The payload exists only as AES-256-GCM
    ciphertext; label and category are non-sensitive metadata used for
    authorization decisions and listings."""

    __tablename__ = "protected_records"

    id = db.Column(db.String(32), primary_key=True, default=new_record_id)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category = db.Column(db.String(30), nullable=False)
    label = db.Column(db.String(120), nullable=False)
    key_id = db.Column(db.String(32), nullable=False)
    nonce = db.Column(db.String(24), nullable=False)  # base64 of 12-byte nonce
    ciphertext = db.Column(db.Text, nullable=False)  # base64 ciphertext + GCM tag
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    owner = db.relationship("User")

    def to_metadata(self):
        return {
            "id": self.id,
            "owner": self.owner.to_public(),
            "category": self.category,
            "label": self.label,
            "key_id": self.key_id,
            "created_at": to_iso(self.created_at),
        }
