"""Consents (permissions), personal records and the activity log."""

from datetime import timedelta

from flask import Blueprint, request

from audit_log import add_log, verify_chain
from detection import find_alerts
from encryption import encrypt
from log_text import Describer, reason_text
from models import CATEGORIES, PURPOSES, Consent, LogEntry, Record, User, db, now
from permissions import update_expiry, view_record
from routes.auth import login_required

bp = Blueprint("data", __name__, url_prefix="/api")


def user_names():
    return {u.id: u.name for u in User.query.all()}


# ---------- Home page numbers ----------

@bp.get("/summary")
@login_required()
def summary(user):
    if user.role == "user":
        my_logs = LogEntry.query.filter(LogEntry.owner_id == user.id, LogEntry.action == "record.view")
        return {"cards": [
            ["My data records", Record.query.filter_by(owner_id=user.id).count()],
            ["Active permissions", Consent.query.filter_by(user_id=user.id, status="active").count()],
            ["Views allowed", my_logs.filter(LogEntry.result == "allowed").count()],
            ["Requests blocked", my_logs.filter(LogEntry.result == "denied").count()],
        ]}
    if user.role == "company":
        my_logs = LogEntry.query.filter(LogEntry.user_id == user.id, LogEntry.action == "record.view")
        return {"cards": [
            ["Permissions received", Consent.query.filter_by(company_id=user.id).count()],
            ["Still active", Consent.query.filter_by(company_id=user.id, status="active").count()],
            ["Views allowed", my_logs.filter(LogEntry.result == "allowed").count()],
            ["Requests blocked", my_logs.filter(LogEntry.result == "denied").count()],
        ]}
    all_logs = LogEntry.query.order_by(LogEntry.id).all()
    return {"cards": [
        ["Log entries", len(all_logs)],
        ["Blocked requests", LogEntry.query.filter_by(action="record.view", result="denied").count()],
        ["Alerts", len(find_alerts(all_logs, user_names()))],
        ["Permissions", Consent.query.count()],
    ]}


# ---------- Consents ----------

@bp.get("/companies")
@login_required()
def companies(user):
    rows = User.query.filter_by(role="company").order_by(User.name).all()
    return {"companies": [{"id": c.id, "name": c.name} for c in rows], "purposes": PURPOSES, "categories": CATEGORIES}


@bp.get("/consents")
@login_required()
def list_consents(user):
    if user.role == "user":
        query = Consent.query.filter_by(user_id=user.id)
    elif user.role == "company":
        query = Consent.query.filter_by(company_id=user.id)
    else:
        query = Consent.query  # investigators see all consents
    consents = query.order_by(Consent.id.desc()).all()
    for consent in consents:
        update_expiry(consent)
    return {"consents": [c.to_dict() for c in consents]}


@bp.post("/consents")
@login_required("user")
def give_consent(user):
    data = request.get_json(silent=True) or {}
    company = db.session.get(User, data.get("company_id") or 0)
    purpose = data.get("purpose")
    categories = data.get("categories") or []
    days = data.get("days")

    if company is None or company.role != "company":
        return {"error": "Please choose a company."}, 400
    if purpose not in PURPOSES:
        return {"error": "Please choose a purpose."}, 400
    if not categories or any(c not in CATEGORIES for c in categories):
        return {"error": "Please choose at least one type of data."}, 400
    if days not in (None, "") and (not str(days).isdigit() or int(days) < 1):
        return {"error": "Days must be a positive number."}, 400

    existing = Consent.query.filter_by(user_id=user.id, company_id=company.id, purpose=purpose, status="active").first()
    if existing:
        return {"error": "You already gave this company permission for this purpose. Withdraw it first."}, 400

    consent = Consent(
        user_id=user.id, company_id=company.id, purpose=purpose,
        categories=",".join(sorted(categories)),
        expires_at=now() + timedelta(days=int(days)) if days else None,
    )
    db.session.add(consent)
    db.session.commit()
    add_log("consent.give", "success", user_id=user.id, owner_id=user.id, target=f"consent {consent.id}",
            details=f"company={company.username}, purpose={purpose}, categories={consent.categories}")
    return {"consent": consent.to_dict()}, 201


@bp.post("/consents/<int:consent_id>/withdraw")
@login_required("user")
def withdraw_consent(user, consent_id):
    consent = db.session.get(Consent, consent_id)
    if consent is None or consent.user_id != user.id:
        return {"error": "Permission not found."}, 404
    update_expiry(consent)
    if consent.status != "active":
        return {"error": f"This permission is already {consent.status}."}, 400

    consent.status = "withdrawn"
    consent.withdrawn_at = now()
    db.session.commit()
    add_log("consent.withdraw", "success", user_id=user.id, owner_id=user.id, target=f"consent {consent.id}",
            details=f"company={consent.company.username}, purpose={consent.purpose}")
    return {"consent": consent.to_dict()}


# ---------- Records ----------

@bp.get("/records")
@login_required("user", "company")
def list_records(user):
    if user.role == "user":
        records = Record.query.filter_by(owner_id=user.id).all()
        return {"records": [r.to_dict() for r in records], "purposes": PURPOSES, "categories": CATEGORIES}

    # A company sees the list (not the content) of records of users who gave it any permission,
    # plus the purposes its ACTIVE permissions allow for each record (empty = not shared)
    consents = Consent.query.filter_by(company_id=user.id).all()
    for consent in consents:
        update_expiry(consent)
    owner_ids = {c.user_id for c in consents}
    records = Record.query.filter(Record.owner_id.in_(owner_ids)).all() if owner_ids else []
    rows = []
    for record in records:
        row = record.to_dict()
        row["allowed_purposes"] = sorted({
            c.purpose for c in consents
            if c.user_id == record.owner_id and c.status == "active" and record.category in c.category_list()
        })
        rows.append(row)
    return {"records": rows, "purposes": PURPOSES, "categories": CATEGORIES}


@bp.post("/records")
@login_required("user")
def add_record(user):
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    category = data.get("category")
    content = (data.get("content") or "").strip()
    if not title or not content:
        return {"error": "Please fill in the title and the content."}, 400
    if category not in CATEGORIES:
        return {"error": "Please choose a type of data."}, 400

    record = Record(owner_id=user.id, title=title, category=category, encrypted_content=encrypt(content))
    db.session.add(record)
    db.session.commit()
    add_log("record.add", "success", user_id=user.id, owner_id=user.id, target=f"record {record.id}")
    return {"record": record.to_dict()}, 201


@bp.post("/records/<int:record_id>/view")
@login_required("user", "company")
def view(user, record_id):
    record = db.session.get(Record, record_id)
    if record is None:
        return {"error": "Record not found."}, 404
    purpose = (request.get_json(silent=True) or {}).get("purpose")
    allowed, reason, content = view_record(user, record, purpose)
    if not allowed:
        return {"error": "Access blocked: you do not have permission.", "reason": reason,
                "reason_text": reason_text(reason)}, 403
    return {"record": record.to_dict(), "content": content}


# ---------- Activity log ----------

@bp.get("/logs")
@login_required()
def list_logs(user):
    query = LogEntry.query
    if user.role == "user":
        query = query.filter((LogEntry.user_id == user.id) | (LogEntry.owner_id == user.id))
    elif user.role == "company":
        query = query.filter(LogEntry.user_id == user.id)
    entries = query.order_by(LogEntry.id.desc()).limit(300).all()
    describer = Describer()
    return {"logs": [describer.row(e) for e in entries]}


@bp.get("/logs/verify")
@login_required()
def verify(user):
    result = verify_chain()
    add_log("log.verify", "success" if result["valid"] else "failed", user_id=user.id,
            details=f"entries={result['count']}")
    return result
