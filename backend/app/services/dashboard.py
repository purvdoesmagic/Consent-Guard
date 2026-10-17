"""Role-scoped dashboard statistics, computed from live database data."""

from sqlalchemy import func

from app.models import AuditEvent, Consent, InvestigationCase
from app.services import audit
from app.services.audit_query import scoped_query, serialize_events
from app.services.consent import refresh_many
from app.utils.time import utcnow


def _consent_query(user):
    if user.role == "subject":
        return Consent.query.filter_by(subject_id=user.id)
    if user.role == "processor":
        return Consent.query.filter_by(recipient_id=user.id)
    return Consent.query


def _access_query(user):
    query = AuditEvent.query.filter(AuditEvent.event_type == "record.access")
    if user.role == "subject":
        return query.filter(AuditEvent.subject_id == user.id)
    if user.role == "processor":
        return query.filter(AuditEvent.actor_id == user.id)
    return query


def build_dashboard(user):
    # Materialize any lapsed expiries first so counts are accurate.
    due = _consent_query(user).filter(Consent.status == "active", Consent.expires_at.isnot(None),
                                      Consent.expires_at <= utcnow()).all()
    refresh_many(due)

    consent_counts = dict(
        _consent_query(user).with_entities(Consent.status, func.count(Consent.id)).group_by(Consent.status).all()
    )
    access_counts = dict(
        _access_query(user).with_entities(AuditEvent.outcome, func.count(AuditEvent.id))
        .group_by(AuditEvent.outcome).all()
    )
    recent = scoped_query(user).order_by(AuditEvent.seq.desc()).limit(8).all()
    integrity = audit.verify_chain()

    open_cases = None
    if user.role == "investigator":
        open_cases = InvestigationCase.query.filter(InvestigationCase.investigator_id == user.id,
                                                    InvestigationCase.status != "closed").count()

    return {
        "role": user.role,
        "consents": {
            "active": consent_counts.get("active", 0),
            "withdrawn": consent_counts.get("withdrawn", 0),
            "expired": consent_counts.get("expired", 0),
        },
        "access": {
            "total": sum(access_counts.values()),
            "allowed": access_counts.get("allowed", 0),
            "denied": access_counts.get("denied", 0),
            "failed": access_counts.get("failure", 0),
        },
        "open_cases": open_cases,
        "integrity": {
            "valid": integrity["valid"],
            "event_count": integrity["event_count"],
            "finding_count": len(integrity["findings"]),
            "checked_at": integrity["checked_at"],
        },
        "recent_events": serialize_events(recent),
    }
