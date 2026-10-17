from flask import Blueprint

from app.constants import CASE_STATUSES, DATA_CATEGORIES, NOTE_TYPES, PURPOSES, RECORD_ACTIONS
from app.models import User
from app.security.sessions import login_required, roles_required

bp = Blueprint("meta", __name__, url_prefix="/api")


@bp.get("/meta")
@login_required
def meta():
    return {
        "purposes": [{"code": k, "label": v} for k, v in PURPOSES.items()],
        "categories": [{"code": k, "label": v} for k, v in DATA_CATEGORIES.items()],
        "record_actions": sorted(RECORD_ACTIONS),
        "case_statuses": sorted(CASE_STATUSES),
        "note_types": sorted(NOTE_TYPES),
    }


@bp.get("/processors")
@roles_required("subject")
def processors():
    """Directory of data processors a subject can grant consent to."""
    users = User.query.filter_by(role="processor", is_active=True).order_by(User.display_name).all()
    return {"processors": [u.to_public() for u in users]}
