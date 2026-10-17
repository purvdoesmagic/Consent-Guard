// Display helpers. All timestamps are shown in UTC to match the audit trail.

export function formatTimestamp(iso, { seconds = true } = {}) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const text = date.toISOString().replace("T", " ");
  return `${seconds ? text.slice(0, 19) : text.slice(0, 16)} UTC`;
}

export function toIsoFromLocalInput(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

export function humanize(code) {
  if (!code) return "—";
  return code.replace(/[_.]/g, " ").replace(/\s+/g, " ").trim().replace(/^\w/, (c) => c.toUpperCase());
}

export const REASON_TEXT = {
  ALLOW_OWNER: "Allowed: you own this record.",
  ALLOW_CONSENT: "Allowed by an active consent covering this purpose and data category.",
  ACCESS_DENIED: "Access denied. No ownership or applicable consent exists.",
  DENY_CONSENT_WITHDRAWN: "Denied: the subject withdrew the consent that covered this access.",
  DENY_CONSENT_EXPIRED: "Denied: the applicable consent has expired.",
  DENY_PURPOSE_NOT_COVERED: "Denied: the subject has not consented to this purpose.",
  DENY_CATEGORY_NOT_COVERED: "Denied: this data category is not covered by the consent for this purpose.",
  DENY_ACTION_NOT_PERMITTED: "Denied: consents only authorize reading, not this action.",
  DENY_ACTION_NOT_SUPPORTED: "Denied: this action is not supported for records.",
  DENY_PURPOSE_INVALID: "Denied: a valid processing purpose is required.",
  DENY_INVALID_ACTION: "Denied: unknown action.",
  DENY_NO_CONSENT: "Denied: no consent exists between the subject and requester.",
  DENY_ROLE_NOT_PERMITTED: "Denied: this role may not access other users' records.",
  DENY_RESOURCE_NOT_FOUND: "Denied: the record does not exist.",
};

export function outcomeTone(outcome) {
  return { allowed: "success", success: "success", denied: "danger", failure: "danger", info: "info" }[outcome] ?? "neutral";
}

export function statusTone(status) {
  return (
    {
      active: "success",
      withdrawn: "danger",
      expired: "warning",
      open: "primary",
      under_review: "warning",
      closed: "neutral",
    }[status] ?? "neutral"
  );
}

export function personLabel(person, fallbackId) {
  if (person) return `${person.display_name} (${person.username})`;
  return fallbackId ? `User #${fallbackId}` : "—";
}
