from flask import Blueprint, g, request

from app.constants import CONSENT_STATUSES, DATA_CATEGORIES, PURPOSES
from app.extensions import db
from app.models import Consent
from app.security.sessions import (
    deny_investigator_without_mfa, investigator_mfa_satisfied, login_required, roles_required,
)
from app.services import audit
from app.services.consent import create_consent, refresh_many, update_consent, withdraw_consent
from app.utils.errors import ApiError
from app.utils.validation import get_choice, get_choice_list, get_int, get_timestamp, json_body, query_int

bp = Blueprint("consents", __name__, url_prefix="/api/consents")


def _load(consent_id, *, write=False):
    """Fetch a consent the current user may see (or modify, if write=True).
    Anything else is reported as 404 so IDs cannot be probed."""
    user = g.user
    if user.role == "investigator" and not investigator_mfa_satisfied(user, g.session):
        deny_investigator_without_mfa()
    consent = db.session.get(Consent, consent_id)
    if consent is not None:
        if consent.subject_id == user.id:
            return consent
        if not write and (consent.recipient_id == user.id or user.role == "investigator"):
            return consent
    audit.record("authz.denied", "denied", actor_id=user.id, subject_id=consent.subject_id if consent else None,
                 resource_type="consent", resource_id=consent_id, action="write" if write else "read",
                 reason_code="NOT_RESOURCE_OWNER" if consent else "RESOURCE_NOT_FOUND")
    raise ApiError(404, "NOT_FOUND", "Consent not found.")


@bp.get("")
@login_required
def list_consents():
    user = g.user
    query = Consent.query
    if user.role == "subject":
        query = query.filter_by(subject_id=user.id)
    elif user.role == "processor":
        query = query.filter_by(recipient_id=user.id)
    else:
        if not investigator_mfa_satisfied(user, g.session):
            deny_investigator_without_mfa()
        for field in ("subject_id", "recipient_id"):
            value = query_int(field, minimum=1)
            if value:
                query = query.filter(getattr(Consent, field) == value)
    consents = refresh_many(query.order_by(Consent.created_at.desc()).all())
    status = request.args.get("status")
    if status:
        if status not in CONSENT_STATUSES:
            raise ApiError(400, "VALIDATION_ERROR", "Unknown status filter.", {"field": "status"})
        consents = [c for c in consents if c.status == status]
    return {"consents": [c.to_dict() for c in consents]}


@bp.post("")
@roles_required("subject")
def create():
    data = json_body()
    consent = create_consent(
        g.user,
        get_int(data, "recipient_id", minimum=1),
        get_choice(data, "purpose", set(PURPOSES)),
        get_choice_list(data, "categories", set(DATA_CATEGORIES)),
        get_timestamp(data, "expires_at", required=False),
    )
    return {"consent": consent.to_dict(include_history=True)}, 201


@bp.get("/<int:consent_id>")
@login_required
def detail(consent_id):
    consent = _load(consent_id)
    refresh_many([consent])
    return {"consent": consent.to_dict(include_history=True)}


@bp.patch("/<int:consent_id>")
@roles_required("subject")
def update(consent_id):
    consent = _load(consent_id, write=True)
    data = json_body()
    unknown = set(data) - {"categories", "expires_at", "clear_expiry"}
    if unknown:
        raise ApiError(400, "VALIDATION_ERROR",
                       "Only categories and expiry can be changed; purpose and recipient are fixed.",
                       {"field": sorted(unknown)[0]})
    consent = update_consent(
        consent, g.user,
        categories=get_choice_list(data, "categories", set(DATA_CATEGORIES), required=False),
        expires_at=get_timestamp(data, "expires_at", required=False),
        clear_expiry=data.get("clear_expiry") is True,
    )
    return {"consent": consent.to_dict(include_history=True)}


@bp.post("/<int:consent_id>/withdraw")
@roles_required("subject")
def withdraw(consent_id):
    consent = withdraw_consent(_load(consent_id, write=True), g.user)
    return {"consent": consent.to_dict(include_history=True)}
