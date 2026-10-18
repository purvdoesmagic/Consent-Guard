"""Database tables (SQLAlchemy models)."""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

ROLES = ["user", "company", "investigator"]
PURPOSES = ["service", "research", "marketing", "analytics"]
CATEGORIES = ["contact", "health", "financial", "location"]


def now():
    """Current time in UTC (stored without timezone info)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # user / company / investigator
    password_hash = db.Column(db.String(200), nullable=False)
    totp_secret = db.Column(db.Text)  # encrypted; empty when two-step login is off

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "name": self.name,
            "role": self.role,
            "two_step_enabled": bool(self.totp_secret),
        }


class Consent(db.Model):
    """A user's permission for one company to use some data for one purpose."""

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    purpose = db.Column(db.String(30), nullable=False)
    categories = db.Column(db.String(200), nullable=False)  # e.g. "health,contact"
    status = db.Column(db.String(20), nullable=False, default="active")  # active / withdrawn / expired
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    expires_at = db.Column(db.DateTime)
    withdrawn_at = db.Column(db.DateTime)

    user = db.relationship("User", foreign_keys=[user_id])
    company = db.relationship("User", foreign_keys=[company_id])

    def category_list(self):
        return self.categories.split(",")

    def to_dict(self):
        return {
            "id": self.id,
            "user": self.user.name,
            "company": self.company.name,
            "purpose": self.purpose,
            "categories": self.category_list(),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }


class Record(db.Model):
    """A piece of personal data. The content is stored encrypted."""

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    category = db.Column(db.String(30), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    encrypted_content = db.Column(db.Text, nullable=False)

    owner = db.relationship("User")

    def to_dict(self):
        # Never includes the content: it has to be requested through the permission check
        return {"id": self.id, "owner": self.owner.name, "category": self.category, "title": self.title}


class LogEntry(db.Model):
    """One line of the activity log. Each entry stores the hash of the
    entry before it, so the entries form a chain (see audit_log.py)."""

    id = db.Column(db.Integer, primary_key=True)
    time = db.Column(db.String(30), nullable=False)
    user_id = db.Column(db.Integer)   # who did it
    owner_id = db.Column(db.Integer)  # whose data it was about
    action = db.Column(db.String(40), nullable=False)
    target = db.Column(db.String(80))
    result = db.Column(db.String(20), nullable=False)  # success / failed / allowed / denied
    reason = db.Column(db.String(40))
    details = db.Column(db.String(200), default="")
    prev_hash = db.Column(db.String(64), nullable=False)
    hash = db.Column(db.String(64), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "time": self.time,
            "user_id": self.user_id,
            "owner_id": self.owner_id,
            "action": self.action,
            "target": self.target,
            "result": self.result,
            "reason": self.reason,
            "details": self.details,
            "hash": self.hash,
        }


# Which log entries belong to which investigation case
case_logs = db.Table(
    "case_logs",
    db.Column("case_id", db.Integer, db.ForeignKey("case.id"), primary_key=True),
    db.Column("log_id", db.Integer, db.ForeignKey("log_entry.id"), primary_key=True),
)


class Case(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default="")
    notes = db.Column(db.Text, default="")
    investigator_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    logs = db.relationship("LogEntry", secondary=case_logs, order_by="LogEntry.id")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
            "log_count": len(self.logs),
        }
