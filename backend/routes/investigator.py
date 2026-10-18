"""Investigator pages: alerts, cases and the PDF report."""

from flask import Blueprint, Response, request

import forensics
from audit_log import add_log, verify_chain
from detection import find_alerts
from models import Case, LogEntry, db
from report import make_pdf
from routes.auth import login_required
from routes.data import user_names

bp = Blueprint("investigator", __name__, url_prefix="/api")


@bp.get("/alerts")
@login_required("investigator")
def alerts(user):
    entries = LogEntry.query.order_by(LogEntry.id).all()
    return {"alerts": find_alerts(entries, user_names())}


@bp.get("/cases")
@login_required("investigator")
def list_cases(user):
    cases = Case.query.filter_by(investigator_id=user.id).order_by(Case.id.desc()).all()
    return {"cases": [c.to_dict() for c in cases]}


@bp.post("/cases")
@login_required("investigator")
def create_case(user):
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return {"error": "Please enter a title."}, 400
    case = Case(title=title, description=(data.get("description") or "").strip(), investigator_id=user.id)
    db.session.add(case)
    db.session.commit()
    add_log("case.create", "success", user_id=user.id, target=f"case {case.id}")
    return {"case": case.to_dict()}, 201


def get_case(user, case_id):
    case = db.session.get(Case, case_id)
    if case is None or case.investigator_id != user.id:
        return None
    return case


@bp.get("/cases/<int:case_id>")
@login_required("investigator")
def case_detail(user, case_id):
    case = get_case(user, case_id)
    if case is None:
        return {"error": "Case not found."}, 404
    names = user_names()
    logs = [dict(e.to_dict(), who=names.get(e.user_id, "-"), owner=names.get(e.owner_id, "")) for e in case.logs]
    return {"case": case.to_dict(), "logs": logs}


@bp.post("/cases/<int:case_id>/logs")
@login_required("investigator")
def link_logs(user, case_id):
    case = get_case(user, case_id)
    if case is None:
        return {"error": "Case not found."}, 404
    ids = (request.get_json(silent=True) or {}).get("log_ids") or []
    entries = LogEntry.query.filter(LogEntry.id.in_(ids)).all()
    for entry in entries:
        if entry not in case.logs:
            case.logs.append(entry)
    db.session.commit()
    add_log("case.link_logs", "success", user_id=user.id, target=f"case {case.id}",
            details="log ids " + ",".join(str(e.id) for e in entries))
    return {"case": case.to_dict()}


@bp.put("/cases/<int:case_id>/notes")
@login_required("investigator")
def save_notes(user, case_id):
    case = get_case(user, case_id)
    if case is None:
        return {"error": "Case not found."}, 404
    case.notes = (request.get_json(silent=True) or {}).get("notes") or ""
    db.session.commit()
    add_log("case.notes", "success", user_id=user.id, target=f"case {case.id}")
    return {"case": case.to_dict()}


@bp.get("/cases/<int:case_id>/report")
@login_required("investigator")
def report(user, case_id):
    case = get_case(user, case_id)
    if case is None:
        return {"error": "Case not found."}, 404
    pdf = make_pdf(case, verify_chain(), user_names(), user.name)
    add_log("case.report", "success", user_id=user.id, target=f"case {case.id}")
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="case-{case.id}-report.pdf"'})


# ---------- Forensics (see forensics.py) ----------

@bp.get("/evidence")
@login_required("investigator")
def list_evidence(user):
    return {"copies": forensics.list_copies()}


@bp.post("/evidence")
@login_required("investigator")
def save_evidence(user):
    note = ((request.get_json(silent=True) or {}).get("note") or "").strip()
    info = forensics.save_copy(user, note)
    add_log("evidence.save", "success", user_id=user.id, target=f"evidence copy {info['id']}",
            details=f"entries={info['entries']}")
    return {"copy": info}, 201


@bp.post("/evidence/<int:copy_id>/compare")
@login_required("investigator")
def compare_evidence(user, copy_id):
    info = forensics.get_copy(copy_id)
    if info is None:
        return {"error": "Evidence copy not found."}, 404
    result = forensics.compare(info)
    add_log("evidence.compare", "failed" if result["tampered"] else "success", user_id=user.id,
            target=f"evidence copy {copy_id}", details=f"missing={len(result['missing'])}")
    return result


@bp.post("/evidence/<int:copy_id>/restore")
@login_required("investigator")
def restore_evidence(user, copy_id):
    info = forensics.get_copy(copy_id)
    if info is None:
        return {"error": "Evidence copy not found."}, 404
    forensics.restore(info)
    add_log("evidence.restore", "success", user_id=user.id, target=f"evidence copy {copy_id}")
    return {"message": f"Database restored from evidence copy {copy_id}."}


@bp.post("/demo/cover-up")
@login_required("investigator")
def demo_cover_up(user):
    """DEMO ONLY: pretend to be an insider editing the database directly (not logged, like a real insider)."""
    company = (request.get_json(silent=True) or {}).get("company") or "quickloans"
    removed = forensics.simulate_cover_up(company)
    return {"removed": removed, "company": company}
