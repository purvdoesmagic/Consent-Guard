"""Consent lifecycle.

States: ``active`` -> ``withdrawn`` (by the subject, terminal)
        ``active`` -> ``expired``   (when ``expires_at`` passes, terminal)

Rules:
* Only the data subject can create, update or withdraw their consent.
* Purpose and recipient are immutable; a new purpose needs a new consent.
* Only an ``active`` consent may be updated (categories and/or expiry).
* Withdrawn and expired consents can never be reactivated.
* At most one active consent per (subject, recipient, purpose).
* Expiry is applied lazily: any read or authorization check first calls
  ``refresh_expiry`` so an expired consent can never authorize access.
* Every change writes a ConsentVersion snapshot and an audit event in the
  same transaction.
"""

from datetime import timedelta

from app.constants import DATA_CATEGORIES, PURPOSES
from app.extensions import db
from app.models import Consent, ConsentVersion, User
from app.services import audit
from app.utils.errors import ApiError
from app.utils.time import to_iso, utcnow

MIN_EXPIRY = timedelta(minutes=1)
MAX_EXPIRY = timedelta(days=3 * 365)


def _snapshot(consent, change_type, changed_by, now):
    db.session.add(ConsentVersion(
        consent_id=consent.id, version=consent.version, change_type=change_type, status=consent.status,
        categories=list(consent.categories), expires_at=consent.expires_at, changed_at=now, changed_by=changed_by,
    ))


def _validate_expiry(expires_at, now):
    if expires_at is None:
        return
    if expires_at < now + MIN_EXPIRY:
        raise ApiError(400, "VALIDATION_ERROR", "Expiry must be at least one minute in the future.",
                       {"field": "expires_at"})
    if expires_at > now + MAX_EXPIRY:
        raise ApiError(400, "VALIDATION_ERROR", "Expiry cannot be more than three years ahead.",
                       {"field": "expires_at"})


def refresh_expiry(consent, now=None):
    """Transition an active consent past its expiry to ``expired``.
    Stages the change; the caller's next audit.commit() persists it."""
    now = now or utcnow()
    if consent.status == "active" and consent.expires_at is not None and consent.expires_at <= now:
        consent.status = "expired"
        consent.expired_at = consent.expires_at
        consent.updated_at = now
        consent.version += 1
        _snapshot(consent, "expired", None, now)
        audit.stage("consent.expired", "info", subject_id=consent.subject_id, resource_type="consent",
                    resource_id=consent.id, action="expire", consent_id=consent.id,
                    details={"expires_at": to_iso(consent.expires_at), "recipient_id": consent.recipient_id,
                             "purpose": consent.purpose})
        return True
    return False


def refresh_many(consents, now=None):
    now = now or utcnow()
    changed = [c for c in consents if refresh_expiry(c, now)]
    if changed:
        audit.commit()
    return consents


def create_consent(subject, recipient_id, purpose, categories, expires_at):
    now = utcnow()
    if purpose not in PURPOSES:
        raise ApiError(400, "VALIDATION_ERROR", "Unknown purpose.", {"field": "purpose"})
    if not categories or any(c not in DATA_CATEGORIES for c in categories):
        raise ApiError(400, "VALIDATION_ERROR", "Invalid data categories.", {"field": "categories"})
    recipient = db.session.get(User, recipient_id)
    if recipient is None or recipient.role != "processor" or not recipient.is_active:
        raise ApiError(400, "VALIDATION_ERROR", "Recipient must be an active data processor.",
                       {"field": "recipient_id"})
    _validate_expiry(expires_at, now)

    existing = Consent.query.filter_by(subject_id=subject.id, recipient_id=recipient_id, purpose=purpose,
                                       status="active").all()
    refresh_many(existing, now)
    if any(c.status == "active" for c in existing):
        raise ApiError(409, "CONSENT_EXISTS",
                       "An active consent for this recipient and purpose already exists. Update it instead.")

    consent = Consent(subject_id=subject.id, recipient_id=recipient_id, purpose=purpose,
                      categories=sorted(set(categories)), status="active", version=1, created_at=now,
                      updated_at=now, expires_at=expires_at)
    db.session.add(consent)
    db.session.flush()
    _snapshot(consent, "created", subject.id, now)
    audit.stage("consent.created", "success", actor_id=subject.id, subject_id=subject.id, resource_type="consent",
                resource_id=consent.id, action="create", consent_id=consent.id,
                details={"recipient_id": recipient_id, "purpose": purpose, "categories": consent.categories,
                         "expires_at": to_iso(expires_at)})
    audit.commit()
    return consent


def update_consent(consent, actor, categories=None, expires_at=None, clear_expiry=False):
    now = utcnow()
    refresh_many([consent], now)
    if consent.status != "active":
        audit.record("consent.update_rejected", "denied", actor_id=actor.id, subject_id=consent.subject_id,
                     resource_type="consent", resource_id=consent.id, action="update", consent_id=consent.id,
                     reason_code=f"CONSENT_{consent.status.upper()}")
        raise ApiError(409, "INVALID_TRANSITION",
                       f"A {consent.status} consent cannot be modified. Create a new consent instead.")

    changes = {}
    if categories is not None:
        if any(c not in DATA_CATEGORIES for c in categories) or not categories:
            raise ApiError(400, "VALIDATION_ERROR", "Invalid data categories.", {"field": "categories"})
        new = sorted(set(categories))
        if new != list(consent.categories):
            changes["categories"] = {"from": list(consent.categories), "to": new}
            consent.categories = new
    if clear_expiry:
        if consent.expires_at is not None:
            changes["expires_at"] = {"from": to_iso(consent.expires_at), "to": None}
            consent.expires_at = None
    elif expires_at is not None:
        _validate_expiry(expires_at, now)
        if expires_at != consent.expires_at:
            changes["expires_at"] = {"from": to_iso(consent.expires_at), "to": to_iso(expires_at)}
            consent.expires_at = expires_at
    if not changes:
        raise ApiError(400, "NO_CHANGES", "The update does not change the consent.")

    consent.version += 1
    consent.updated_at = now
    _snapshot(consent, "updated", actor.id, now)
    audit.stage("consent.updated", "success", actor_id=actor.id, subject_id=consent.subject_id,
                resource_type="consent", resource_id=consent.id, action="update", consent_id=consent.id,
                details={"changes": changes, "version": consent.version})
    audit.commit()
    return consent


def withdraw_consent(consent, actor):
    now = utcnow()
    refresh_many([consent], now)
    if consent.status != "active":
        audit.record("consent.withdraw_rejected", "denied", actor_id=actor.id, subject_id=consent.subject_id,
                     resource_type="consent", resource_id=consent.id, action="withdraw", consent_id=consent.id,
                     reason_code=f"CONSENT_{consent.status.upper()}")
        raise ApiError(409, "INVALID_TRANSITION", f"A {consent.status} consent cannot be withdrawn.")
    consent.status = "withdrawn"
    consent.withdrawn_at = now
    consent.updated_at = now
    consent.version += 1
    _snapshot(consent, "withdrawn", actor.id, now)
    audit.stage("consent.withdrawn", "success", actor_id=actor.id, subject_id=consent.subject_id,
                resource_type="consent", resource_id=consent.id, action="withdraw", consent_id=consent.id,
                details={"recipient_id": consent.recipient_id, "purpose": consent.purpose})
    audit.commit()
    return consent
