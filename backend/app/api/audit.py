from flask import Blueprint, g

from app.models import AuditEvent
from app.security.sessions import login_required, roles_required
from app.services import audit
from app.services.audit_query import apply_filters, paginate, scoped_query, serialize_events
from app.utils.errors import ApiError

bp = Blueprint("audit", __name__, url_prefix="/api/audit")

INTEGRITY_EXPLANATION = {
    "proves": [
        "Every stored event still matches the SHA-256 hash computed when it was written.",
        "Each event links to the hash of its predecessor, so deleting, inserting or reordering "
        "events in the middle of the chain is detected.",
        "If a previous verification checkpoint exists, the chain still contains that head event.",
    ],
    "does_not_prove": [
        "That events were never rewritten by someone with full database and application access who "
        "recomputed every subsequent hash.",
        "That the newest events were not removed when no later checkpoint exists outside the database.",
        "That the recorded facts were true when written (the log records what the application observed).",
    ],
}


@bp.get("/events")
@login_required
def list_events():
    return paginate(apply_filters(scoped_query(g.user)))


@bp.get("/events/<event_id>")
@login_required
def get_event(event_id):
    event = scoped_query(g.user).filter(AuditEvent.event_id == event_id).first()
    if event is None:
        raise ApiError(404, "NOT_FOUND", "Event not found.")
    return {"event": serialize_events([event])[0]}


@bp.get("/integrity")
@login_required
def integrity_status():
    """Read-only status for dashboards. Findings detail is investigator-only."""
    result = audit.verify_chain()
    body = {k: result[k] for k in ("valid", "event_count", "head_seq", "checked_at")}
    body["finding_count"] = len(result["findings"])
    if g.user.role == "investigator":
        body.update(head_hash=result["head_hash"], findings=result["findings"],
                    last_checkpoint=result["last_checkpoint"])
    body["explanation"] = INTEGRITY_EXPLANATION
    return body


@bp.post("/verify")
@roles_required("investigator")
def verify():
    result = audit.verify_and_checkpoint(g.user.id)
    result["explanation"] = INTEGRITY_EXPLANATION
    return result
