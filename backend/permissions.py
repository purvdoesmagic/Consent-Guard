"""The permission check: may this person see this record?

A company can see a user's record only if ALL of these are true:
    1. the user gave the company permission (consent)
    2. the permission is for the same purpose the company is asking for
    3. the permission is still active (not withdrawn, not expired)
       and covers the record's category (e.g. "health")

Every attempt is written to the activity log, allowed or not.
"""

from audit_log import add_log
from encryption import decrypt
from models import Consent, db, now


def update_expiry(consent):
    """Mark an active consent as expired once its end date has passed."""
    if consent.status == "active" and consent.expires_at and consent.expires_at <= now():
        consent.status = "expired"
        db.session.commit()


def check_permission(user, record, purpose):
    """Returns (allowed, reason)."""
    if record.owner_id == user.id:
        return True, "OWNER"
    if user.role != "company":
        return False, "NOT_A_COMPANY"

    consents = Consent.query.filter_by(user_id=record.owner_id, company_id=user.id).all()
    for consent in consents:
        update_expiry(consent)

    # 1. Did the user give any permission?
    if not consents:
        return False, "NO_CONSENT"

    # 2. Is there a permission for this purpose?
    same_purpose = [c for c in consents if c.purpose == purpose]
    if not same_purpose:
        return False, "WRONG_PURPOSE"

    # 3. Is it active and does it cover this kind of data?
    covers_category = [c for c in same_purpose if record.category in c.category_list()]
    for consent in covers_category:
        if consent.status == "active":
            return True, "ALLOWED"
    if covers_category:
        newest = max(covers_category, key=lambda c: c.id)
        return False, "CONSENT_WITHDRAWN" if newest.status == "withdrawn" else "CONSENT_EXPIRED"
    return False, "CATEGORY_NOT_ALLOWED"


def view_record(user, record, purpose):
    """Run the permission check, log the attempt and return the content if allowed."""
    allowed, reason = check_permission(user, record, purpose)
    add_log(
        "record.view",
        "allowed" if allowed else "denied",
        user_id=user.id,
        owner_id=record.owner_id,
        target=f"record {record.id}",
        reason=reason,
        details=f"purpose={purpose}, category={record.category}",
    )
    if not allowed:
        return False, reason, None
    return True, reason, decrypt(record.encrypted_content)
