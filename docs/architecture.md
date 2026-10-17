# ConsentGuard – Architecture

## 1. Overview

```
┌──────────────────────────── Browser ────────────────────────────┐
│ React SPA (Vite build)                                           │
│  pages/  ── hooks/useAuth, useApi ── services/api.js (fetch)     │
│  Route guards shape navigation only; no authorization in React   │
└───────────────┬─────────────────────────────────────────────────┘
                │ same origin  /api/*   cookie cg_session (HttpOnly, SameSite=Strict)
                │ writes add X-CSRF-Token; JSON bodies only
┌───────────────▼─────────────────────────────────────────────────┐
│ Flask app factory (app/__init__.py)                              │
│  before_request: request id → load_session → csrf_protect        │
│  after_request : session cookie, security headers, X-Request-ID  │
│                                                                  │
│  api/ (blueprints: thin HTTP layer, validation, decorators)      │
│   │                                                              │
│   ├─► security/  passwords (Argon2id) · sessions (+CSRF, role    │
│   │              decorators) · mfa (TOTP, recovery) · crypto     │
│   │              (AES-256-GCM) · headers                         │
│   ├─► services/  consent lifecycle · authorization (decision     │
│   │              point) · records (encrypt/decrypt/access) ·     │
│   │              audit (hash chain) · audit_query · dashboard    │
│   ├─► investigations/ cases (evidence, timeline, notes) ·        │
│   │              detection (rules R1–R7)                         │
│   └─► reports/   pdf (ReportLab)                                 │
│                                                                  │
│  models/ (SQLAlchemy ORM) ──► SQLite (backend/instance/*.db)     │
└──────────────────────────────────────────────────────────────────┘
 Secrets: CG_ENCRYPTION_KEY from project-root .env (never in the DB)
```

In development, Vite (127.0.0.1:5173) serves the SPA and proxies `/api` to Flask (127.0.0.1:5000), so the browser
sees one origin. After `npm run build`, Flask serves `frontend/dist` itself.

## 2. Layering rules

| Layer | Responsibility | Must not |
| --- | --- | --- |
| `api/` | Parse/validate input, call services, shape JSON | Contain business rules or SQL beyond simple lookups |
| `security/` | Authentication, sessions, CSRF, crypto primitives | Know about consents or investigations |
| `services/` | Business rules, authorization decisions, audit writing | Read HTTP request bodies |
| `investigations/`, `reports/` | Forensic workflow and output | Bypass the audit service |
| `models/` | Persistence schema | Contain business logic |

## 3. Request lifecycle (example: processor reads a record)

1. `POST /api/records/<id>/access {action, purpose}` with cookie + `X-CSRF-Token`.
2. `load_session` hashes the cookie token, finds the session, checks revocation, absolute and idle expiry.
3. `csrf_protect` checks the Origin allow-list and compares the CSRF header to the session's token (constant time).
4. `roles_required("subject","processor","investigator")` ensures a fully authenticated session (and MFA for investigators).
5. `records.access_record` loads the record and calls `authorization.evaluate_record_access`.
6. The decision service refreshes expiry of every relevant consent, applies the ordered rules and returns
   `Decision(allowed, reason, consent_id)`.
7. If allowed, the ciphertext is decrypted with AAD bound to record id/owner/category.
8. `audit.stage("record.access", …)` then `audit.commit()` writes any consent-expiry events and the access event in
   one transaction under the chain lock.
9. Response: payload (allowed) or `403` with a safe reason code (denied).

## 4. Data model

```
users 1─* user_sessions
users 1─* recovery_codes
users 1─* consents (as subject)      consents 1─* consent_versions
users 1─* consents (as recipient)
users 1─* protected_records
users 1─* investigation_cases (lead) investigation_cases 1─* case_events *─1 audit_events
                                     investigation_cases 1─* case_notes
audit_events (standalone chain; references ids without FKs)    audit_checkpoints
```

Key constraints: `users.username` unique · `user_sessions.token_hash` unique · `consent_versions(consent_id,
version)` unique · `audit_events.seq/event_id/prev_hash/hash` unique · `case_events(case_id, audit_event_id)` unique.
Schema is managed by Alembic (`backend/migrations`); tests use `db.create_all()` on temporary databases.

## 5. Audit event schema

| Field | Meaning |
| --- | --- |
| `seq` | Position in chain (1..n) |
| `event_id` | UUIDv4 |
| `timestamp` | UTC, `YYYY-MM-DDTHH:MM:SS.ffffffZ`, stored exactly as hashed |
| `event_type` | e.g. `auth.login.failure`, `consent.withdrawn`, `record.access`, `case.report_generated` |
| `actor_id` | User performing the action (null for anonymous/system) |
| `subject_id` | Owner of the affected data/account |
| `resource_type` / `resource_id` | e.g. `record` / record UUID |
| `action` | e.g. `read`, `withdraw`, `login` |
| `outcome` | `allowed`, `denied`, `success`, `failure`, `info` |
| `reason_code` | e.g. `DENY_CONSENT_WITHDRAWN`, `INVALID_CREDENTIALS`, `SESSION_IDLE_TIMEOUT` |
| `consent_id` | Consent that authorized or was relevant to the decision |
| `request_id` | Correlates with the `X-Request-ID` response header and error bodies |
| `details_json` | Canonical JSON, non-sensitive context (purpose, category, counts); keys like `password`, `secret`, `token`, `payload` are rejected |
| `prev_hash`, `hash` | Chain integrity |

Event types recorded: registration; login success/failure; MFA challenge, success, failure, enable/disable, recovery
regeneration; logout; session rejection (expired/idle/unknown); session revocation; password change; reauth failure;
authorization denials (endpoint, consent, case); consent created/updated/withdrawn/expired and rejected transitions;
record created/accessed (allowed/denied/decryption failure); audit verification; case created/updated, evidence
linked/unlinked, note added, report generated.

Data minimisation: no IP addresses, user agents (except in the user's own session list), plaintext, passwords or
raw failed usernames (only a pseudonymous SHA-256 fingerprint) are stored in events.

## 6. Concurrency

`audit.commit()` holds a process-wide `threading.Lock` from reading the chain head until the transaction commits.
The Flask dev server is threaded, so this serializes writers in the single local process. Across processes the
UNIQUE constraints on `seq` and `prev_hash` make a conflicting insert fail (the request returns 500 and nothing is
committed) instead of creating a fork. `test_concurrent_writers_keep_chain_valid` runs 6 threads × 15 writes and
verifies a valid 90-event chain.

## 7. Frontend structure

| Folder | Contents |
| --- | --- |
| `services/api.js` | fetch wrapper: CSRF header, error normalisation, file download |
| `hooks/useAuth.jsx` | Session state machine: loading → anonymous / mfa / authenticated |
| `hooks/useApi.js` | `useApi(path)` loader and `useAction()` for forms |
| `components/` | Layout (role-based navigation), EventTable, EventFilters, IndicatorList, badges, feedback states |
| `pages/` | Auth, Dashboard, Consents (list/create/detail), Records, Audit, Integrity, Cases, CaseDetail, Detection, Account |
| `styles/app.css` | Design tokens and components; responsive breakpoint at 900 px |

All pages call the real API. Tests mock `fetch` only in frontend unit/integration tests.
