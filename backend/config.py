"""Settings for the ConsentGuard server.

Secrets are read from the .env file in the project root
(create it with: python scripts/setup_env.py).
"""

import os
from datetime import timedelta

from dotenv import load_dotenv

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BACKEND_DIR, "..", ".env"))


class Config:
    # Signs the login cookie. If it is missing we use a random one,
    # which simply means everyone is logged out when the server restarts.
    SECRET_KEY = os.environ.get("CG_SECRET_KEY") or os.urandom(32)

    # The database file is created in backend/instance/
    SQLALCHEMY_DATABASE_URI = "sqlite:///consentguard.db"

    # 32-byte key (base64) used to encrypt personal data
    ENCRYPTION_KEY = os.environ.get("CG_ENCRYPTION_KEY")

    # Log users out after 30 minutes
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Block login after this many wrong passwords in LOCKOUT_MINUTES
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 5
