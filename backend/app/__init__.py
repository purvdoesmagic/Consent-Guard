"""ConsentGuard Flask application factory."""

import logging
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, request, send_from_directory
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.config import BACKEND_DIR, PROJECT_ROOT, load_config
from app.extensions import db, limiter, migrate
from app.security.crypto import Cipher
from app.security.headers import apply_security_headers
from app.utils.errors import register_error_handlers

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _record):
    if dbapi_connection.__class__.__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


def create_app(overrides=None):
    if not (overrides or {}).get("TESTING"):
        load_dotenv(PROJECT_ROOT / ".env", override=False)

    app = Flask(__name__, instance_path=str(BACKEND_DIR / "instance"))
    app.config.update(load_config(overrides))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    # Fail closed: refuse to start without a valid encryption key.
    app.extensions["cg_cipher"] = Cipher(app.config["ENCRYPTION_KEY"], app.config["ENCRYPTION_KEY_ID"])

    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if uri.startswith("sqlite:///") and ":memory:" not in uri:
        Path(uri[len("sqlite:///"):]).parent.mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(BACKEND_DIR / "migrations"), render_as_batch=True)
    limiter.init_app(app)

    from app import models  # noqa: F401  (register models with SQLAlchemy)
    from app.api import register_blueprints
    from app.cli import register_cli
    from app.security.sessions import apply_session_cookie, csrf_protect, load_session
    from app.services import audit

    register_blueprints(app)
    register_error_handlers(app)
    register_cli(app)

    @app.before_request
    def _before():
        g.request_id = str(uuid.uuid4())
        g.new_session_token = None
        g.clear_session_cookie = False
        if request.path.startswith("/api/"):
            load_session()
            csrf_protect()

    @app.after_request
    def _after(response):
        response.headers["X-Request-ID"] = g.get("request_id", "")
        apply_session_cookie(response)
        return apply_security_headers(
            response, hsts=app.config["COOKIE_SECURE"], is_api=request.path.startswith("/api/")
        )

    @app.teardown_request
    def _teardown(_exc):
        audit.discard()

    # Serve the production frontend build (if present) from the same origin.
    @app.get("/")
    @app.get("/<path:path>")
    def frontend(path=""):
        if path.startswith("api/"):
            from app.utils.errors import ApiError

            raise ApiError(404, "NOT_FOUND", "Unknown API endpoint.")
        if not FRONTEND_DIST.exists():
            return {"message": "ConsentGuard API. Run the frontend dev server (npm run dev) or build it."}, 200
        target = FRONTEND_DIST / path
        if path and target.is_file() and FRONTEND_DIST in target.resolve().parents:
            return send_from_directory(FRONTEND_DIST, path)
        return send_from_directory(FRONTEND_DIST, "index.html")

    return app
