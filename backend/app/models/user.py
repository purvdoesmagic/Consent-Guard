from app.extensions import db
from app.utils.time import to_iso, utcnow


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    display_name = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="subject")
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    # MFA: secrets are stored AES-GCM encrypted, never in plaintext.
    mfa_enabled = db.Column(db.Boolean, nullable=False, default=False)
    mfa_secret_enc = db.Column(db.Text, nullable=True)
    mfa_pending_secret_enc = db.Column(db.Text, nullable=True)
    mfa_last_timestep = db.Column(db.Integer, nullable=True)  # TOTP replay protection

    def to_public(self):
        return {"id": self.id, "username": self.username, "display_name": self.display_name, "role": self.role}

    def to_self(self):
        data = self.to_public()
        data.update(
            mfa_enabled=self.mfa_enabled,
            created_at=to_iso(self.created_at),
            recovery_codes_remaining=sum(1 for c in self.recovery_codes if c.used_at is None),
        )
        return data


class UserSession(db.Model):
    """Server-side session. The cookie holds a random token; only its SHA-256 is stored."""

    __tablename__ = "user_sessions"

    id = db.Column(db.Integer, primary_key=True)
    token_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    csrf_token = db.Column(db.String(64), nullable=False)
    mfa_pending = db.Column(db.Boolean, nullable=False, default=False)
    mfa_verified = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    revoked_at = db.Column(db.DateTime, nullable=True)
    user_agent = db.Column(db.String(200), nullable=True)

    user = db.relationship("User")

    def to_dict(self, current_id=None):
        return {
            "id": self.id,
            "created_at": to_iso(self.created_at),
            "last_seen_at": to_iso(self.last_seen_at),
            "expires_at": to_iso(self.expires_at),
            "mfa_verified": self.mfa_verified,
            "user_agent": self.user_agent,
            "current": self.id == current_id,
        }


class RecoveryCode(db.Model):
    __tablename__ = "recovery_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    code_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    used_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("recovery_codes", lazy="select"))
