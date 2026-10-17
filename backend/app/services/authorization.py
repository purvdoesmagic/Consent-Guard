"""Backend authorization service for protected-record access.

``evaluate_record_access`` is the single decision point used by the records
API. It is deny-by-default: every path that does not reach an explicit ALLOW
returns a DENY decision with a reason code. Rules, in order:

 1. Record must exist                         -> else DENY_RESOURCE_NOT_FOUND
 2. Action must be a known action             -> else DENY_INVALID_ACTION
 3. Owner: may ``read``/``export`` own record -> ALLOW_OWNER
           other actions are not supported    -> DENY_ACTION_NOT_SUPPORTED
 4. Non-owner must have role ``processor``    -> else DENY_ROLE_NOT_PERMITTED
 5. Processors may only ``read``              -> else DENY_ACTION_NOT_PERMITTED
 6. Purpose must be a known processing purpose -> else DENY_PURPOSE_INVALID
 7. Load consents subject->processor (expiry refreshed first)
    none at all                               -> DENY_NO_CONSENT
 8. An ACTIVE consent whose purpose equals the request purpose AND whose
    categories include the record's category -> ALLOW_CONSENT
 9. Otherwise the most specific denial:
    a. a non-active consent matching purpose AND category exists
       -> DENY_CONSENT_WITHDRAWN / DENY_CONSENT_EXPIRED (most recent one)
    b. an active consent for the purpose exists (category not covered)
       -> DENY_CATEGORY_NOT_COVERED
    c. a non-active consent for the purpose exists
       -> DENY_CONSENT_WITHDRAWN / DENY_CONSENT_EXPIRED
    d. otherwise                              -> DENY_PURPOSE_NOT_COVERED

The full reason is always recorded in the audit event. The client sees the
specific reason only for 9a-9d, where the requester already knows the consent
relationship exists; for 1, 4 and 7 it sees a generic ACCESS_DENIED so the
API cannot be used to discover which records or relationships exist.
"""

from dataclasses import dataclass

from app.constants import PURPOSES, RECORD_ACTIONS
from app.models import Consent
from app.services.consent import refresh_expiry
from app.utils.time import utcnow

OWNER_ACTIONS = {"read", "export"}
PROCESSOR_ACTIONS = {"read"}
DISCLOSABLE_REASONS = {
    "DENY_CONSENT_WITHDRAWN", "DENY_CONSENT_EXPIRED", "DENY_CATEGORY_NOT_COVERED",
    "DENY_PURPOSE_NOT_COVERED", "DENY_ACTION_NOT_PERMITTED", "DENY_ACTION_NOT_SUPPORTED",
    "DENY_PURPOSE_INVALID", "DENY_INVALID_ACTION",
}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    consent_id: int | None = None

    @property
    def public_reason(self):
        if self.allowed:
            return self.reason
        return self.reason if self.reason in DISCLOSABLE_REASONS else "ACCESS_DENIED"


def _deny(reason, consent_id=None):
    return Decision(False, reason, consent_id)


def _latest(consents):
    return max(consents, key=lambda c: (c.updated_at, c.id))


def _status_reason(consent):
    return _deny("DENY_CONSENT_WITHDRAWN" if consent.status == "withdrawn" else "DENY_CONSENT_EXPIRED", consent.id)


def evaluate_record_access(user, record, action, purpose, now=None):
    now = now or utcnow()
    if user is None:
        return _deny("DENY_UNAUTHENTICATED")
    if record is None:
        return _deny("DENY_RESOURCE_NOT_FOUND")
    if action not in RECORD_ACTIONS:
        return _deny("DENY_INVALID_ACTION")

    if record.owner_id == user.id:
        return Decision(True, "ALLOW_OWNER") if action in OWNER_ACTIONS else _deny("DENY_ACTION_NOT_SUPPORTED")

    if user.role != "processor":
        return _deny("DENY_ROLE_NOT_PERMITTED")
    if action not in PROCESSOR_ACTIONS:
        return _deny("DENY_ACTION_NOT_PERMITTED")
    if purpose not in PURPOSES:
        return _deny("DENY_PURPOSE_INVALID")

    consents = Consent.query.filter_by(subject_id=record.owner_id, recipient_id=user.id).all()
    for consent in consents:
        refresh_expiry(consent, now)
    if not consents:
        return _deny("DENY_NO_CONSENT")

    for_purpose = [c for c in consents if c.purpose == purpose]
    exact = [c for c in for_purpose if record.category in c.categories]
    exact_active = [c for c in exact if c.status == "active"]
    if exact_active:
        return Decision(True, "ALLOW_CONSENT", _latest(exact_active).id)
    if exact:
        return _status_reason(_latest(exact))
    active_for_purpose = [c for c in for_purpose if c.status == "active"]
    if active_for_purpose:
        return _deny("DENY_CATEGORY_NOT_COVERED", _latest(active_for_purpose).id)
    if for_purpose:
        return _status_reason(_latest(for_purpose))
    return _deny("DENY_PURPOSE_NOT_COVERED")
