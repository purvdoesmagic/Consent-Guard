# ConsentGuard – API reference

Base path `/api`. JSON in and out (except the PDF). Authentication: `cg_session` cookie. Every POST/PATCH/DELETE made
with a session must include `X-CSRF-Token` (value from `/auth/session`, login or MFA responses).

Errors: `{"error": {"code", "message", "request_id", "details?"}}`. Common codes: `VALIDATION_ERROR` (400),
`UNSUPPORTED_MEDIA_TYPE` (415), `AUTHENTICATION_REQUIRED` / `MFA_REQUIRED` (401), `FORBIDDEN`,
`MFA_ENROLLMENT_REQUIRED`, `CSRF_TOKEN_INVALID`, `CSRF_ORIGIN_REJECTED` (403), `NOT_FOUND` (404),
`INVALID_TRANSITION` / `CONSENT_EXISTS` (409), `PAYLOAD_TOO_LARGE` (413), `RATE_LIMITED` (429), `INTERNAL_ERROR` (500).

Roles: **S** subject, **P** processor, **I** investigator (MFA required), **any** = any signed-in user.

## Health and metadata

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| GET | `/health` | public | `{status, database, time}` |
| GET | `/meta` | any | Purposes, categories, record actions, case statuses, note types |
| GET | `/processors` | S | Processors a subject can grant consent to |
| GET | `/dashboard` | any | Role-scoped counts (consents, access, open cases), integrity status, 8 recent events |

## Authentication and account

| Method | Path | Access | Body → Response |
| --- | --- | --- | --- |
| GET | `/auth/session` | public | `{authenticated, mfa_pending, user, csrf_token, session_expires_at}` |
| POST | `/auth/register` | public (10/h) | `{username, display_name, password, role: subject\|processor}` → 201 `{user}` |
| POST | `/auth/login` | public (rate limited) | `{username, password}` → `{mfa_required: true, csrf_token}` or session payload |
| POST | `/auth/mfa/verify` | pending session (rate limited) | `{code}` or `{recovery_code}` → session payload (new token) |
| POST | `/auth/logout` | any | Revokes session, clears cookie |
| GET | `/auth/me` | any | `{user}` incl. `mfa_enabled`, `recovery_codes_remaining` |
| POST | `/auth/mfa/setup` | any | → `{secret, otpauth_uri, qr_svg_data_uri}` (pending secret stored encrypted) |
| POST | `/auth/mfa/enable` | any | `{code}` → `{user, recovery_codes[10]}` (other sessions revoked) |
| POST | `/auth/mfa/disable` | any | `{password, code}` |
| POST | `/auth/mfa/recovery-codes` | any | `{password, code}` → `{recovery_codes}` |
| POST | `/auth/password` | any | `{current_password, new_password}` → `{sessions_revoked}` |
| GET | `/auth/sessions` | any | Own active sessions |
| POST | `/auth/sessions/revoke-others` | any | → `{sessions_revoked}` |

## Consents

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| GET | `/consents?status=` | any | S: own; P: granted to me; I: all (`subject_id`, `recipient_id` filters) |
| POST | `/consents` | S | `{recipient_id, purpose, categories[], expires_at?}` → 201 |
| GET | `/consents/<id>` | owner, recipient, I | Consent with `history[]`; others get 404 |
| PATCH | `/consents/<id>` | owner S | `{categories?, expires_at?, clear_expiry?}`; purpose/recipient rejected; non-active → 409 |
| POST | `/consents/<id>/withdraw` | owner S | Active → withdrawn; otherwise 409 |

## Protected records

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| GET | `/records` | S, P | Metadata only. S: own. P: records of subjects who granted them any consent |
| POST | `/records` | S | `{label, category, fields: {name: value}}` (≤12 fields) → encrypted, 201 metadata |
| POST | `/records/<id>/access` | S, P, I | `{action: read\|export\|update\|delete, purpose?}` → `{decision, consent_id, payload}` or 403 `{details.reason}` |

Every access request writes a `record.access` event (allowed, denied or failure).

## Audit

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| GET | `/audit/events` | any (scoped) | Filters: `start`, `end` (ISO), `actor_id`, `subject_id`, `consent_id`, `resource_id`, `resource_type`, `action`, `reason_code`, `outcome`, `event_type` (prefix); `page`, `page_size` (≤200), `order=asc\|desc` |
| GET | `/audit/events/<event_id>` | any (scoped) | Single event |
| GET | `/audit/integrity` | any | Read-only status; investigators also get findings, head hash, checkpoint |
| POST | `/audit/verify` | I | Full verification, records checkpoint and `audit.verified` event |

Scope: I = all events; S = events they performed or about their data; P = events they performed.

## Investigations

| Method | Path | Access | Description |
| --- | --- | --- | --- |
| GET | `/cases?status=` | I | Cases led by the caller |
| POST | `/cases` | I | `{title, description?, scope_start?, scope_end?}` → 201 |
| GET | `/cases/<id>` | lead I | `{case, notes}`; other users 404 (denial logged) |
| PATCH | `/cases/<id>` | lead I | `{title?, description?, status?, status_note?}`; closed → under_review needs `status_note` |
| GET | `/cases/<id>/events` | lead I | Linked events (accepts audit filters) |
| POST | `/cases/<id>/events` | lead I | `{event_ids[], rationale?}` → `{linked}` (idempotent) |
| DELETE | `/cases/<id>/events/<event_id>` | lead I | Unlink (audited) |
| GET | `/cases/<id>/timeline` | lead I | Linked events + consent history, chronological (accepts audit filters) |
| POST | `/cases/<id>/notes` | lead I | `{note_type: note\|finding\|conclusion, content}` → 201 |
| GET | `/cases/<id>/indicators` | lead I | Rules over linked events; optional `window_minutes`, `denial_threshold`, `probing_threshold`, `failed_login_threshold` |
| GET | `/cases/<id>/report.pdf` | lead I | PDF attachment; writes `case.report_generated` |
| GET | `/detection/indicators` | I | Rules over all events (audit filters + thresholds; ≤5000 newest events) |
