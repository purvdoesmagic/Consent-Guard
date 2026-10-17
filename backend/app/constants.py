"""Controlled vocabularies shared by the consent, authorization and audit layers."""

ROLES = {"subject", "processor", "investigator"}
SELF_REGISTER_ROLES = {"subject", "processor"}  # investigators are created via CLI only

PURPOSES = {
    "service_delivery": "Service delivery",
    "medical_research": "Medical research",
    "insurance_assessment": "Insurance assessment",
    "marketing": "Marketing communications",
    "analytics": "Aggregated analytics",
}

DATA_CATEGORIES = {
    "contact": "Contact details",
    "demographic": "Demographic data",
    "health": "Health data",
    "financial": "Financial data",
    "location": "Location data",
}

# Actions a requester may ask for on a protected record. Only "read" is
# permitted by any policy in this version; the others exist so the
# authorization service can demonstrate action-based denial.
RECORD_ACTIONS = {"read", "export", "update", "delete"}

CONSENT_STATUSES = {"active", "withdrawn", "expired"}
CASE_STATUSES = {"open", "under_review", "closed"}
CASE_STATUS_TRANSITIONS = {
    "open": {"under_review", "closed"},
    "under_review": {"open", "closed"},
    "closed": {"under_review"},  # re-opening requires a justification note
}
NOTE_TYPES = {"note", "finding", "conclusion"}
