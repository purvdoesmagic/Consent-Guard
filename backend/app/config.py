"""Application configuration loaded from environment variables.

Values come from the process environment, optionally populated from the
project-root ``.env`` file (see ``.env.example``). Secrets are never given
defaults here: a missing encryption key stops the application from starting.
"""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


def _bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name, default):
    value = os.environ.get(name)
    return int(value) if value not in (None, "") else default


def _database_url():
    url = os.environ.get("CG_DATABASE_URL", "sqlite:///instance/consentguard.db")
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith(prefix + "/"):
        relative = url[len(prefix):]
        if relative and relative != ":memory:" and not Path(relative).is_absolute():
            url = prefix + str((BACKEND_DIR / relative).resolve()).replace("\\", "/")
    return url


class Config:
    ENV_NAME = os.environ.get("CG_ENV", "development")
    TESTING = False

    SQLALCHEMY_DATABASE_URI = None  # resolved in load_config()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Encryption (validated by app.security.crypto at startup)
    ENCRYPTION_KEY = None
    ENCRYPTION_KEY_ID = "k1"

    # Sessions
    SESSION_COOKIE_NAME = "cg_session"
    COOKIE_SECURE = False
    SESSION_IDLE_MINUTES = 30
    SESSION_ABSOLUTE_HOURS = 8
    PENDING_MFA_MINUTES = 5

    REQUIRE_MFA_FOR_INVESTIGATORS = True

    # Argon2id parameters (OWASP-recommended baseline: m=19 MiB, t=2, p=1)
    ARGON2_TIME_COST = 2
    ARGON2_MEMORY_COST = 19456
    ARGON2_PARALLELISM = 1

    # Rate limiting
    RATELIMIT_ENABLED = True
    RATELIMIT_STORAGE_URI = "memory://"
    RATELIMIT_HEADERS_ENABLED = True
    LOGIN_RATE_LIMIT = "5 per minute;30 per hour"
    MFA_RATE_LIMIT = "5 per minute;30 per hour"
    REGISTER_RATE_LIMIT = "10 per hour"

    ALLOWED_ORIGINS = []

    # Detection-rule thresholds (see docs/investigation-methodology in README)
    DETECTION_WINDOW_MINUTES = 10
    DETECTION_DENIAL_THRESHOLD = 3
    DETECTION_PROBING_THRESHOLD = 3
    DETECTION_FAILED_LOGIN_THRESHOLD = 5

    MAX_CONTENT_LENGTH = 64 * 1024


def load_config(overrides=None):
    """Build a config dict from defaults, environment variables and overrides."""
    cfg = {k: getattr(Config, k) for k in dir(Config) if k.isupper()}
    cfg.update(
        SQLALCHEMY_DATABASE_URI=_database_url(),
        ENCRYPTION_KEY=os.environ.get("CG_ENCRYPTION_KEY"),
        ENCRYPTION_KEY_ID=os.environ.get("CG_ENCRYPTION_KEY_ID", "k1"),
        COOKIE_SECURE=_bool("CG_COOKIE_SECURE", Config.ENV_NAME == "production"),
        SESSION_IDLE_MINUTES=_int("CG_SESSION_IDLE_MINUTES", Config.SESSION_IDLE_MINUTES),
        SESSION_ABSOLUTE_HOURS=_int("CG_SESSION_ABSOLUTE_HOURS", Config.SESSION_ABSOLUTE_HOURS),
        REQUIRE_MFA_FOR_INVESTIGATORS=_bool("CG_REQUIRE_MFA_FOR_INVESTIGATORS", True),
        LOGIN_RATE_LIMIT=os.environ.get("CG_LOGIN_RATE_LIMIT", Config.LOGIN_RATE_LIMIT),
        MFA_RATE_LIMIT=os.environ.get("CG_MFA_RATE_LIMIT", Config.MFA_RATE_LIMIT),
        ALLOWED_ORIGINS=[
            o.strip()
            for o in os.environ.get(
                "CG_ALLOWED_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5000,http://127.0.0.1:5000",
            ).split(",")
            if o.strip()
        ],
    )
    if overrides:
        cfg.update(overrides)
    return cfg
