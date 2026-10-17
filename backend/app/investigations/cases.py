"""Investigation case management.

Access model: a case is visible only to its lead investigator (the creator).
Notes and evidence links are append-only from the API's point of view;
unlinking an event is allowed but recorded in the audit trail. Every case
action writes an audit event, so the investigation itself is accountable.
"""

from flask import current_app

from app.constants import CASE_STATUS_TRANSITIONS, CASE_STATUSES, NOTE_TYPES
from app.extensions import db
from app.investigations.detection import Thresholds, run_rules
from app.models import AuditEvent, CaseEvent, CaseNote, Consent, ConsentVersion, InvestigationCase, User
from app.services import audit
from app.services.audit_query import apply_filters, serialize_events
from app.utils.errors import ApiError
from app.utils.time import to_iso, utcnow

MAX_LINK_BATCH = 200


def _next_case_number(now):
    prefix = f"CG-{now.year}-"
    last = (InvestigationCase.query.filter(InvestigationCase.case_number.like(prefix + "%"))
            .order_by(InvestigationCase.case_number.desc()).first())
    number = int(last.case_number.rsplit("-", 1)[1]) + 1 if last else 1
    return f"{prefix}{number:04d}"


def _case_event(case, event_type, action, actor, details=None):
    audit.stage(event_type, "success", actor_id=actor.id, resource_type="case", resource_id=case.id,
                action=action, details=dict(details or {}, case_number=case.case_number))


def load_case(user, case_id):
    case = db.session.get(InvestigationCase, case_id)
    if case is not None and case.investigator_id == user.id:
        return case
    audit.record("authz.denied", "denied", actor_id=user.id, resource_type="case", resource_id=case_id,
                 action="read", reason_code="NOT_CASE_INVESTIGATOR" if case else "RESOURCE_NOT_FOUND")
    raise ApiError(404, "NOT_FOUND", "Case not found.")


def create_case(user, title, description, scope_start, scope_end):
    if scope_start and scope_end and scope_start > scope_end:
        raise ApiError(400, "VALIDATION_ERROR", "Scope start must be before scope end.", {"field": "scope_start"})
    now = utcnow()
    case = InvestigationCase(case_number=_next_case_number(now), title=title, description=description or "",
                             status="open", investigator_id=user.id, scope_start=scope_start, scope_end=scope_end,
                             created_at=now, updated_at=now)
    db.session.add(case)
    db.session.flush()
    _case_event(case, "case.created", "create", user, {"title": title})
    audit.commit()
    return case


def update_case(case, user, title=None, description=None, status=None, status_note=None):
    changes = {}
    if title is not None and title != case.title:
        changes["title"] = True
        case.title = title
    if description is not None and description != case.description:
        changes["description"] = True
        case.description = description
    if status is not None and status != case.status:
        if status not in CASE_STATUSES or status not in CASE_STATUS_TRANSITIONS[case.status]:
            raise ApiError(409, "INVALID_TRANSITION", f"Cannot change case status from {case.status} to {status}.")
        if case.status == "closed" and not status_note:
            raise ApiError(400, "VALIDATION_ERROR", "Re-opening a closed case requires a justification note.",
                           {"field": "status_note"})
        changes["status"] = {"from": case.status, "to": status}
        case.status = status
        case.closed_at = utcnow() if status == "closed" else None
        if status_note:
            db.session.add(CaseNote(case_id=case.id, author_id=user.id, note_type="note",
                                    content=f"[Status change to {status}] {status_note}"))
    if not changes:
        raise ApiError(400, "NO_CHANGES", "The update does not change the case.")
    case.updated_at = utcnow()
    _case_event(case, "case.updated", "update", user, {"changes": changes})
    audit.commit()
    return case


def link_events(case, user, event_ids, rationale):
    if not event_ids or len(event_ids) > MAX_LINK_BATCH:
        raise ApiError(400, "VALIDATION_ERROR", f"Provide 1-{MAX_LINK_BATCH} event IDs.", {"field": "event_ids"})
    events = AuditEvent.query.filter(AuditEvent.event_id.in_(event_ids)).all()
    found = {e.event_id for e in events}
    missing = [eid for eid in event_ids if eid not in found]
    if missing:
        raise ApiError(400, "VALIDATION_ERROR", "Some event IDs do not exist.", {"field": "event_ids",
                                                                                 "missing": missing[:10]})
    already = {link.audit_event_id for link in case.links}
    added = []
    for event in events:
        if event.id not in already:
            db.session.add(CaseEvent(case_id=case.id, audit_event_id=event.id, linked_by=user.id,
                                     rationale=rationale))
            added.append(event.event_id)
    if added:
        case.updated_at = utcnow()
        _case_event(case, "case.events_linked", "link", user, {"event_ids": added[:50], "count": len(added)})
        audit.commit()
    return added


def unlink_event(case, user, event_id):
    link = next((l for l in case.links if l.event.event_id == event_id), None)
    if link is None:
        raise ApiError(404, "NOT_FOUND", "Event is not linked to this case.")
    db.session.delete(link)
    case.updated_at = utcnow()
    _case_event(case, "case.event_unlinked", "unlink", user, {"event_id": event_id})
    audit.commit()


def add_note(case, user, note_type, content):
    if note_type not in NOTE_TYPES:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown note type.", {"field": "note_type"})
    note = CaseNote(case_id=case.id, author_id=user.id, note_type=note_type, content=content, created_at=utcnow())
    db.session.add(note)
    case.updated_at = utcnow()
    db.session.flush()
    _case_event(case, "case.note_added", "annotate", user, {"note_id": note.id, "note_type": note_type})
    audit.commit()
    return note


def linked_events(case, filtered=False):
    query = AuditEvent.query.join(CaseEvent, CaseEvent.audit_event_id == AuditEvent.id).filter(
        CaseEvent.case_id == case.id)
    if filtered:
        query = apply_filters(query)
    return query.order_by(AuditEvent.timestamp.asc(), AuditEvent.seq.asc()).all()


def related_consents(events):
    ids = sorted({e.consent_id for e in events if e.consent_id})
    return Consent.query.filter(Consent.id.in_(ids)).order_by(Consent.id).all() if ids else []


def timeline(case, filtered=True):
    """Chronological merge of linked audit events and the history of every
    consent those events reference."""
    events = linked_events(case, filtered=filtered)
    items = [{"source": "audit_event", "timestamp": e.timestamp, "seq": e.seq, "event": data}
             for e, data in zip(events, serialize_events(events))]
    for consent in related_consents(events):
        for version in ConsentVersion.query.filter_by(consent_id=consent.id).order_by(ConsentVersion.version):
            items.append({"source": "consent_history", "timestamp": to_iso(version.changed_at), "seq": None,
                          "consent_id": consent.id, "consent": {
                              "purpose": consent.purpose, "subject_id": consent.subject_id,
                              "recipient_id": consent.recipient_id}, "version": version.to_dict()})
    items.sort(key=lambda i: (i["timestamp"], 0 if i["source"] == "consent_history" else 1, i["seq"] or 0))
    return items


def thresholds_from_request(args):
    def bounded(name, lo, hi):
        value = args.get(name)
        if value in (None, ""):
            return None
        try:
            number = int(value)
        except ValueError:
            raise ApiError(400, "VALIDATION_ERROR", f"'{name}' must be an integer.", {"field": name})
        if not lo <= number <= hi:
            raise ApiError(400, "VALIDATION_ERROR", f"'{name}' must be between {lo} and {hi}.", {"field": name})
        return number

    return Thresholds.from_config(
        current_app.config,
        window_minutes=bounded("window_minutes", 1, 1440),
        denial_threshold=bounded("denial_threshold", 2, 100),
        probing_threshold=bounded("probing_threshold", 2, 100),
        failed_login_threshold=bounded("failed_login_threshold", 2, 100),
    )


def case_indicators(case, thresholds=None):
    thresholds = thresholds or Thresholds.from_config(current_app.config)
    return run_rules(linked_events(case), thresholds), thresholds


def people_for(events, case):
    """Minimal identity info for users referenced by the case's evidence only."""
    ids = {e.actor_id for e in events if e.actor_id} | {e.subject_id for e in events if e.subject_id}
    for consent in related_consents(events):
        ids |= {consent.subject_id, consent.recipient_id}
    ids.add(case.investigator_id)
    users = User.query.filter(User.id.in_(ids)).all() if ids else []
    return {u.id: u.to_public() for u in users}
