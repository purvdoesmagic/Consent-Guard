import hashlib
import re

from app.constants import ROLES
from app.extensions import db
from app.models import User
from app.security.passwords import hash_secret, validate_password
from app.services import audit

USERNAME_PATTERN = r"[a-z0-9][a-z0-9_.-]{2,31}"


class UserCreationError(ValueError):
    def __init__(self, field, message):
        super().__init__(message)
        self.field = field


def normalize_username(username):
    return (username or "").strip().lower()


def username_fingerprint(username):
    """Pseudonymous identifier for failed-login analysis without storing the
    raw (possibly mistyped, possibly someone's password) username."""
    return hashlib.sha256(("cg-username:" + normalize_username(username)).encode("utf-8")).hexdigest()[:16]


def create_user(username, password, display_name, role, actor_id=None):
    """Create a user and its audit event in one transaction."""
    username = normalize_username(username)
    if not re.fullmatch(USERNAME_PATTERN, username):
        raise UserCreationError("username", "Username must be 3-32 characters: letters, digits, '.', '_' or '-'.")
    if role not in ROLES:
        raise UserCreationError("role", "Unknown role.")
    display_name = (display_name or "").strip()
    if not 1 <= len(display_name) <= 80:
        raise UserCreationError("display_name", "Display name must be 1-80 characters.")
    problems = validate_password(password, username)
    if problems:
        raise UserCreationError("password", " ".join(problems))
    if User.query.filter_by(username=username).first():
        raise UserCreationError("username", "That username is not available.")

    user = User(username=username, display_name=display_name, role=role, password_hash=hash_secret(password))
    db.session.add(user)
    db.session.flush()
    audit.stage("auth.register", "success", actor_id=actor_id or user.id, subject_id=user.id,
                resource_type="user", resource_id=user.id, action="create", details={"role": role})
    audit.commit()
    return user
