from flask import Blueprint
from sqlalchemy import text

from app.extensions import db
from app.utils.time import to_iso, utcnow

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "unavailable"
    status = 200 if database == "ok" else 503
    return {"status": "ok" if status == 200 else "degraded", "database": database, "time": to_iso(utcnow())}, status
