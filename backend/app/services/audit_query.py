"""Role-scoped, filterable queries over audit events."""

from flask import request
from sqlalchemy import or_

from app.models import AuditEvent, User
from app.utils.errors import ApiError
from app.utils.time import to_iso
from app.utils.validation import query_int, query_timestamp

OUTCOMES = {"success", "allowed", "denied", "failure", "info"}


def scoped_query(user):
    """Investigators see every event; subjects see events they performed or
    that concern their data; processors see only events they performed."""
    query = AuditEvent.query
    if user.role == "investigator":
        return query
    if user.role == "subject":
        return query.filter(or_(AuditEvent.actor_id == user.id, AuditEvent.subject_id == user.id))
    return query.filter(AuditEvent.actor_id == user.id)


def apply_filters(query, args=None):
    args = args if args is not None else request.args
    start = query_timestamp("start")
    end = query_timestamp("end")
    if start and end and start > end:
        raise ApiError(400, "VALIDATION_ERROR", "'start' must be before 'end'.", {"field": "start"})
    if start:
        query = query.filter(AuditEvent.timestamp >= to_iso(start))
    if end:
        query = query.filter(AuditEvent.timestamp <= to_iso(end))
    for name in ("actor_id", "subject_id", "consent_id"):
        value = query_int(name, minimum=0)
        if value is not None:
            query = query.filter(getattr(AuditEvent, name) == value)
    for name in ("resource_id", "resource_type", "action", "reason_code"):
        value = args.get(name)
        if value:
            if len(value) > 64:
                raise ApiError(400, "VALIDATION_ERROR", f"'{name}' is too long.", {"field": name})
            query = query.filter(getattr(AuditEvent, name) == value)
    outcome = args.get("outcome")
    if outcome:
        if outcome not in OUTCOMES:
            raise ApiError(400, "VALIDATION_ERROR", "Unknown outcome.", {"field": "outcome"})
        query = query.filter(AuditEvent.outcome == outcome)
    event_type = args.get("event_type")
    if event_type:
        if len(event_type) > 60:
            raise ApiError(400, "VALIDATION_ERROR", "'event_type' is too long.", {"field": "event_type"})
        # Prefix match so "consent." returns all consent events. Escape LIKE wildcards.
        escaped = event_type.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(AuditEvent.event_type.like(escaped + "%", escape="\\"))
    return query


def serialize_events(events):
    """Event dicts with minimal public identity (username, role) of the actor
    and data subject, so viewers can see who acted on whose data."""
    ids = {e.actor_id for e in events if e.actor_id} | {e.subject_id for e in events if e.subject_id}
    people = {u.id: u.to_public() for u in User.query.filter(User.id.in_(ids)).all()} if ids else {}
    out = []
    for e in events:
        data = e.to_dict()
        data["actor"] = people.get(e.actor_id)
        data["subject"] = people.get(e.subject_id)
        out.append(data)
    return out


def paginate(query, default_size=50):
    page = query_int("page", default=1, minimum=1, maximum=100000)
    size = query_int("page_size", default=default_size, minimum=1, maximum=200)
    order = request.args.get("order", "desc")
    ordering = AuditEvent.seq.asc() if order == "asc" else AuditEvent.seq.desc()
    total = query.count()
    items = query.order_by(ordering).offset((page - 1) * size).limit(size).all()
    return {"events": serialize_events(items), "page": page, "page_size": size, "total": total}
