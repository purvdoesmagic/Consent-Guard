"""Consents (permissions), personal records and the activity log."""

from datetime import timedelta

from flask import Blueprint, request

from audit_log import add_log, verify_chain
from encryption import encrypt
from models import CATEGORIES, PURPOSES, Consent, LogEntry, Record, User, db, now
from permissions import update_expiry, view_record
from routes.auth import login_required

bp = Blueprint("data", __name__, url_prefix="/api")


def user_names():
    return {u.id: u.username for u in User.query.all()}


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
    data = request.get_json() or {}
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
    else:
        # A company sees the list (not the content) of records of users who gave it any permission
        owner_ids = {c.user_id for c in Consent.query.filter_by(company_id=user.id)}
        records = Record.query.filter(Record.owner_id.in_(owner_ids)).all() if owner_ids else []
    return {"records": [r.to_dict() for r in records], "purposes": PURPOSES, "categories": CATEGORIES}


@bp.post("/records")
@login_required("user")
def add_record(user):
    data = request.get_json() or {}
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
    purpose = (request.get_json() or {}).get("purpose")
    allowed, reason, content = view_record(user, record, purpose)
    if not allowed:
        return {"error": "Access blocked: you do not have permission.", "reason": reason}, 403
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
    names = user_names()
    rows = []
    for e in entries:
        row = e.to_dict()
        row["who"] = names.get(e.user_id, "-")
        row["owner"] = names.get(e.owner_id, "")
        rows.append(row)
    return {"logs": rows}


@bp.get("/logs/verify")
@login_required()
def verify(user):
    result = verify_chain()
    add_log("log.verify", "success" if result["valid"] else "failed", user_id=user.id,
            details=f"entries={result['count']}")
    return result
