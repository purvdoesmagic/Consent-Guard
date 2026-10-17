from flask import Blueprint, Response, g, request

from app.constants import CASE_STATUSES, NOTE_TYPES
from app.investigations import cases as svc
from app.investigations.detection import run_rules
from app.models import AuditEvent, InvestigationCase
from app.reports.pdf import build_case_report
from app.security.sessions import roles_required
from app.services import audit
from app.services.audit_query import apply_filters, serialize_events
from app.utils.time import to_iso, utcnow
from app.utils.validation import get_choice, get_str, get_timestamp, invalid, json_body, query_timestamp

bp = Blueprint("cases", __name__, url_prefix="/api")


@bp.get("/cases")
@roles_required("investigator")
def list_cases():
    query = InvestigationCase.query.filter_by(investigator_id=g.user.id)
    status = request.args.get("status")
    if status:
        if status not in CASE_STATUSES:
            raise invalid("status", "Unknown status.")
        query = query.filter_by(status=status)
    return {"cases": [c.to_dict() for c in query.order_by(InvestigationCase.created_at.desc()).all()]}


@bp.post("/cases")
@roles_required("investigator")
def create_case():
    data = json_body()
    case = svc.create_case(
        g.user,
        get_str(data, "title", min_len=3, max_len=150),
        get_str(data, "description", required=False, max_len=4000) or "",
        get_timestamp(data, "scope_start", required=False),
        get_timestamp(data, "scope_end", required=False),
    )
    return {"case": case.to_dict()}, 201


@bp.get("/cases/<int:case_id>")
@roles_required("investigator")
def get_case(case_id):
    case = svc.load_case(g.user, case_id)
    return {"case": case.to_dict(), "notes": [n.to_dict() for n in case.notes]}


@bp.patch("/cases/<int:case_id>")
@roles_required("investigator")
def update_case(case_id):
    case = svc.load_case(g.user, case_id)
    data = json_body()
    case = svc.update_case(
        case, g.user,
        title=get_str(data, "title", required=False, min_len=3, max_len=150),
        description=get_str(data, "description", required=False, max_len=4000),
        status=get_choice(data, "status", CASE_STATUSES, required=False),
        status_note=get_str(data, "status_note", required=False, max_len=2000),
    )
    return {"case": case.to_dict(), "notes": [n.to_dict() for n in case.notes]}


@bp.get("/cases/<int:case_id>/events")
@roles_required("investigator")
def case_events(case_id):
    case = svc.load_case(g.user, case_id)
    return {"events": serialize_events(svc.linked_events(case, filtered=True))}


@bp.post("/cases/<int:case_id>/events")
@roles_required("investigator")
def link_events(case_id):
    case = svc.load_case(g.user, case_id)
    data = json_body()
    ids = data.get("event_ids")
    if not isinstance(ids, list) or not all(isinstance(i, str) and len(i) <= 36 for i in ids):
        raise invalid("event_ids", "'event_ids' must be a list of event ID strings.")
    added = svc.link_events(case, g.user, list(dict.fromkeys(ids)),
                            get_str(data, "rationale", required=False, max_len=300))
    return {"linked": added, "case": case.to_dict()}


@bp.delete("/cases/<int:case_id>/events/<event_id>")
@roles_required("investigator")
def unlink_event(case_id, event_id):
    case = svc.load_case(g.user, case_id)
    svc.unlink_event(case, g.user, event_id)
    return {"case": case.to_dict()}


@bp.get("/cases/<int:case_id>/timeline")
@roles_required("investigator")
def case_timeline(case_id):
    case = svc.load_case(g.user, case_id)
    return {"timeline": svc.timeline(case)}


@bp.post("/cases/<int:case_id>/notes")
@roles_required("investigator")
def add_note(case_id):
    case = svc.load_case(g.user, case_id)
    data = json_body()
    note = svc.add_note(case, g.user, get_choice(data, "note_type", NOTE_TYPES),
                        get_str(data, "content", min_len=1, max_len=5000))
    return {"note": note.to_dict()}, 201


@bp.get("/cases/<int:case_id>/indicators")
@roles_required("investigator")
def case_indicators(case_id):
    case = svc.load_case(g.user, case_id)
    indicators, thresholds = svc.case_indicators(case, svc.thresholds_from_request(request.args))
    return {"indicators": indicators, "thresholds": thresholds.as_dict()}


@bp.get("/cases/<int:case_id>/report.pdf")
@roles_required("investigator")
def case_report(case_id):
    case = svc.load_case(g.user, case_id)
    events = svc.linked_events(case)
    indicators, thresholds = svc.case_indicators(case)
    integrity = audit.verify_chain()
    generated_at = to_iso(utcnow())
    pdf = build_case_report(
        case=case, events=events, consents=svc.related_consents(events), indicators=indicators,
        thresholds=thresholds.as_dict(), integrity=integrity, notes=case.notes,
        people=svc.people_for(events, case), generated_at=generated_at, generated_by=g.user.id,
    )
    audit.record("case.report_generated", "success", actor_id=g.user.id, resource_type="case", resource_id=case.id,
                 action="export", details={"case_number": case.case_number, "event_count": len(events),
                                           "indicator_count": len(indicators), "chain_valid": integrity["valid"],
                                           "chain_head_seq": integrity["head_seq"]})
    filename = f"{case.case_number}-report.pdf"
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@bp.get("/detection/indicators")
@roles_required("investigator")
def detection_indicators():
    """Run all rules across every event in a time range to find leads."""
    start = query_timestamp("start")
    end = query_timestamp("end")
    query = apply_filters(AuditEvent.query)
    events = query.order_by(AuditEvent.seq.desc()).limit(5000).all()
    thresholds = svc.thresholds_from_request(request.args)
    return {"indicators": run_rules(events, thresholds), "thresholds": thresholds.as_dict(),
            "events_examined": len(events), "start": to_iso(start), "end": to_iso(end)}
