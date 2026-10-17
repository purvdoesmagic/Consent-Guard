# ConsentGuard – Privacy-Centric User Consent and Data Access Management System

ConsentGuard is a student project that combines **user consent management**, **consent-enforced access to protected
data**, **tamper-evident audit logging**, **rule-based detection of suspicious access** and a **digital-forensics
investigation workflow** with PDF evidence reports.

All data in the system is **synthetic**. Never enter real personal data.

---

## 1. Problem statement and objectives

Organisations that process personal data must be able to show *who accessed what, under which consent, for what
purpose* — and prove that their records have not been quietly altered. In many systems consent is a checkbox stored
separately from access control, logs are mutable, and investigating a privacy complaint means stitching together
unrelated sources.

ConsentGuard demonstrates an integrated design in which:

1. Data subjects grant, adjust and withdraw **purpose- and category-specific consent** to named processors.
2. Every access to protected data is **decided by a backend authorization service that consults consent** (deny by
   default) and is **logged whether allowed or denied**.
3. Logged events form a **SHA-256 hash chain** whose integrity can be verified.
4. Investigators can **detect suspicious patterns** with transparent rules, assemble **cases**, view a **timeline**
   that merges access events with consent history, record findings, and export a **PDF report**.

### Scope

In scope: local single-server deployment, three roles (subject, processor, investigator), synthetic records,
AES-256-GCM encryption at rest, TOTP MFA, CSRF-protected cookie sessions, rate limiting, audit hash chain,
seven detection rules, PDF reports, React UI.
Out of scope: production hosting, multi-tenant organisations, real identity proofing, external anchoring of audit
checkpoints, key-management services (see [Limitations](#14-known-limitations-and-future-work)).

## 2. Features

| Area | What is implemented |
| --- | --- |
| Authentication | Registration, login/logout, Argon2id hashing, password policy, server-side sessions (idle + absolute expiry, revocation), TOTP MFA with QR enrollment, single-use recovery codes, TOTP replay protection, rate limiting on login and MFA, generic error messages, session rotation on login and after MFA |
| Consent | Create, view, update (categories/expiry), withdraw, automatic expiry, append-only version history, invalid-transition rejection, one active consent per recipient+purpose |
| Protected data | Synthetic records encrypted with AES-256-GCM (unique random nonce per encryption, AAD binding to record metadata), key from environment, fail-closed key validation |
| Authorization | Single decision service considering owner, role, action, purpose, category, consent status, withdrawal and expiry; deny by default; IDOR-safe responses |
| Audit | Structured events (UTC timestamp, actor, subject, resource, action, outcome, reason code, consent, request ID, details), SHA-256 hash chain, verification with findings, checkpoints |
| Investigations | Cases, evidence linking, filtered chronological timeline with consent history, 7 detection rules with configurable thresholds, notes/findings/conclusions, case status workflow, every action audited |
| Reports | Deterministic PDF with case overview, scope, observed facts, timeline with event IDs, consents, indicators, integrity result and chain head hash, notes, conclusions and limitations |
| Frontend | React + Vite SPA; dashboard, consents, records, access history, integrity view, cases, timeline, detection, account security; loading/empty/error states; responsive; keyboard accessible |

## 3. Architecture (summary)

```
Browser (React SPA) ──/api (same origin, cookie + X-CSRF-Token)──► Flask REST API
                                                                   ├─ security/  passwords, sessions+CSRF, MFA, AES-GCM, headers
                                                                   ├─ services/  consent lifecycle, authorization, records, audit chain, dashboard
                                                                   ├─ investigations/  cases, detection rules
                                                                   ├─ reports/   PDF generation
                                                                   └─ models/    SQLAlchemy ORM ─► SQLite
Encryption key: environment variable (.env), never in the database.
```

Full details: [docs/architecture.md](docs/architecture.md) · API: [docs/api.md](docs/api.md) ·
Threat model: [docs/threat-model.md](docs/threat-model.md) · Tests: [docs/testing.md](docs/testing.md) ·
Faculty demo: [docs/faculty-demo.md](docs/faculty-demo.md) ·
**Forensic case study:** [docs/case-study.md](docs/case-study.md)

## 4. Folder structure

```
Consent Gaurd/
├─ backend/
│  ├─ app/
│  │  ├─ api/              Flask blueprints (auth, consents, records, audit, cases, dashboard, meta, health)
│  │  ├─ models/           SQLAlchemy models (users, sessions, consents, records, audit, investigations)
│  │  ├─ security/         passwords.py, sessions.py (sessions/CSRF/decorators), mfa.py, crypto.py, headers.py
│  │  ├─ services/         consent.py, authorization.py, records.py, audit.py, audit_query.py, dashboard.py, users.py
│  │  ├─ investigations/   cases.py, detection.py
│  │  ├─ reports/          pdf.py
│  │  ├─ utils/            time, validation, errors
│  │  ├─ cli.py            seed-demo, create-investigator
│  │  ├─ config.py, constants.py, extensions.py, __init__.py (app factory)
│  ├─ migrations/          Alembic migration scripts
│  ├─ tests/               pytest suite (isolated temp databases)
│  ├─ requirements.txt, requirements-dev.txt, pytest.ini, wsgi.py
├─ frontend/
│  ├─ src/ components/ pages/ hooks/ services/ utils/ styles/ test/
│  ├─ public/, index.html, package.json, vite.config.js
├─ docs/                   architecture, api, threat-model, testing, faculty-demo, case-study
├─ scripts/                setup_env.py, totp.py, smoke_test.py, tamper_demo.py,
│                          case_study.py, forensic_examiner.py
├─ .env.example, .gitignore, README.md
```

## 5. Database design

| Table | Purpose / key relationships |
| --- | --- |
| `users` | Accounts; `role` ∈ subject/processor/investigator; Argon2id hash; encrypted MFA secret; last TOTP step |
| `user_sessions` | Server sessions: SHA-256 of cookie token, CSRF token, MFA state, expiry, revocation → `users` |
| `recovery_codes` | Argon2id-hashed single-use MFA recovery codes → `users` |
| `consents` | subject → recipient, purpose, categories (JSON), status, version, timestamps |
| `consent_versions` | Append-only snapshot per lifecycle change → `consents` (unique consent_id+version) |
| `protected_records` | Owner, category, label (metadata), key_id, nonce, ciphertext → `users` |
| `audit_events` | Hash-chained events; unique `seq`, `event_id`, `prev_hash`, `hash` |
| `audit_checkpoints` | Chain head recorded at each explicit verification |
| `investigation_cases` | Case number, title, status, lead investigator, scope → `users` |
| `case_events` | Case ↔ audit event evidence links (unique pair) |
| `case_notes` | Append-only notes typed note/finding/conclusion |

Audit events reference users/consents/resources by ID **without foreign keys**, so evidence remains intact and
verifiable even if referenced rows change.

## 6. Consent and authorization rules

Consent lifecycle: `active → withdrawn` (subject action, terminal) and `active → expired` (when `expires_at` is
reached, applied lazily before any read or decision, terminal). Purpose and recipient are immutable; only active
consents can change categories/expiry; withdrawn/expired consents can never be reactivated (create a new one).

Access decision (`backend/app/services/authorization.py`), evaluated in order:

1. Record must exist → else `DENY_RESOURCE_NOT_FOUND`
2. Action must be known (`read`, `export`, `update`, `delete`) → else `DENY_INVALID_ACTION`
3. Owner may `read`/`export` own record → `ALLOW_OWNER`; other actions → `DENY_ACTION_NOT_SUPPORTED`
4. Non-owners must have role `processor` → else `DENY_ROLE_NOT_PERMITTED` (investigators never see plaintext)
5. Processors may only `read` → else `DENY_ACTION_NOT_PERMITTED`
6. Purpose must be a known purpose → else `DENY_PURPOSE_INVALID`
7. No consent at all from owner to processor → `DENY_NO_CONSENT`
8. An **active** consent with the **same purpose** whose **categories include the record's category** → `ALLOW_CONSENT`
9. Otherwise the most specific denial: matching but withdrawn/expired consent → `DENY_CONSENT_WITHDRAWN` /
   `DENY_CONSENT_EXPIRED`; active consent for the purpose but category missing → `DENY_CATEGORY_NOT_COVERED`;
   non-active consent for the purpose → withdrawn/expired; else `DENY_PURPOSE_NOT_COVERED`.

The full reason is always stored in the audit event. Clients see a specific reason only where the requester already
knows the consent relationship exists; otherwise they see the generic `ACCESS_DENIED` (non-existent and forbidden
records are indistinguishable).

## 7. Security controls (summary)

Argon2id (m=19 MiB, t=2, p=1) · 12+ character password policy with deny-list · server-side sessions storing only
token hashes · HttpOnly + SameSite=Strict (+ Secure when configured) cookies · 30-min idle / 8-h absolute expiry ·
session rotation at login and after MFA · TOTP (RFC 6238, ±1 step, replay-protected) · Argon2id-hashed single-use
recovery codes · synchronizer CSRF token + Origin allow-list + JSON-only bodies · Flask-Limiter on login, MFA and
registration · server-side input validation · ORM-parameterized queries · CSP, X-Frame-Options, nosniff,
Referrer-Policy, Permissions-Policy, COOP/CORP, `Cache-Control: no-store` on the API · generic error bodies with
request IDs · investigators must have MFA · AES-256-GCM with AAD · audit hash chain. See
[docs/threat-model.md](docs/threat-model.md).

## 8. Encryption and key management

* Key: 32 random bytes, URL-safe base64, in `CG_ENCRYPTION_KEY` (project-root `.env`), id in `CG_ENCRYPTION_KEY_ID`.
* `python scripts/setup_env.py` generates `.env` and **never overwrites an existing key**.
* The backend **refuses to start** if the key is missing, still the placeholder, not base64, or not 32 bytes.
* Each encryption uses a fresh 96-bit nonce from the OS CSPRNG; ciphertext, nonce and key id are stored per record.
* AAD = `{purpose, record_id, owner_id, category}` – moving a ciphertext to another record or editing its category
  metadata makes decryption fail. MFA secrets use separate AAD (`mfa-secret`, user id).
* Decryption failures return a generic error, never partial data, and are logged as `DECRYPTION_FAILED`.

**Backup, loss, rotation:** back up `.env` separately from the database (e.g. a password manager). If the key is lost,
encrypted records and MFA secrets are **unrecoverable** (MFA users would need their MFA reset by recreating the
account in this demo). Rotation is *prepared* (each ciphertext stores `key_id`) but not automated: rotation would
require loading old and new keys, re-encrypting every record and MFA secret, then retiring the old key. Production
systems should use a KMS/HSM with envelope encryption.

## 9. Audit hash chain

Each event's hash = SHA-256 over canonical JSON (sorted keys, no whitespace, ASCII) of all event fields plus the
previous event's hash; the first event links to 64 zeros. Timestamps are stored exactly as hashed
(`YYYY-MM-DDTHH:MM:SS.ffffffZ`). Writes take a process lock, read the head and commit the business change and its
events in **one transaction**; `seq` and `prev_hash` are UNIQUE so a concurrent writer cannot fork the chain.

Verification detects: modified events (`HASH_MISMATCH`), deleted events (`SEQUENCE_GAP`, `PREVIOUS_HASH_MISMATCH`),
reordered or inserted events (`PREVIOUS_HASH_MISMATCH`, `HASH_MISMATCH`), timestamp regressions, and truncation
behind a recorded checkpoint (`CHECKPOINT_MISMATCH`).

**What it does not prove:** someone with full control of the database *and* knowledge of the algorithm can rewrite
the whole chain (and the checkpoint table). The chain is **tamper-evident, not immutable**. Stronger options: print
or publish the head hash (every PDF report includes it), periodically sign checkpoints with a key held elsewhere,
push them to an independently controlled append-only store (WORM storage, a transparency log, or a timestamping
authority).

## 10. Investigation methodology and detection rules

1. Run rules over all events (Detection page) or a time window to find leads.
2. Open a case, link supporting events (from the detection page or audit trail).
3. Review the timeline (access events merged with consent history), filter by time/actor/resource/action/consent/outcome.
4. Record notes and findings; record conclusions separately; change status (open → under review → closed).
5. Verify audit integrity; export the PDF report.

| Rule | Trigger (defaults: W = 10 min, N = 3, M = 3, K = 5; windows inclusive) | Severity |
| --- | --- | --- |
| R1 REPEATED_DENIALS | ≥ N denied record accesses by one actor within W | medium (high if ≥ 2N) |
| R2 ACCESS_AFTER_WITHDRAWAL | access denied because consent was withdrawn | high |
| R3 ACCESS_AFTER_EXPIRY | access denied because consent expired | medium |
| R4 PURPOSE_MISMATCH | access requested for a non-consented purpose | medium |
| R5 CATEGORY_MISMATCH | access to a category not covered by consent | medium |
| R6 BROAD_PROBING | one actor denied on ≥ M distinct resources (no consent/ownership) within W | high |
| R7 FAILED_AUTH_BURST | ≥ K failed login/MFA attempts against one account (or one unknown username fingerprint) within W | medium |

Thresholds are configurable in `config.py` and per request (validated). Each indicator lists its supporting event
IDs and timestamps. Indicators are **leads, not proof**; the UI and the PDF keep observed facts, system indicators,
investigator notes/findings and conclusions in separate sections.

## 11. Installation and startup (Windows PowerShell)

Prerequisites: **Python 3.12** (tested 3.12.5), **Node.js ≥ 20.19** (tested 24.21, npm 11.19), Git optional.

```powershell
cd "C:\Users\<you>\OneDrive\Desktop\Consent Gaurd"

# 1. Secrets (.env with a fresh AES-256 key; never overwrites an existing key)
python scripts\setup_env.py

# 2. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\flask.exe --app wsgi db upgrade        # create the SQLite schema (backend\instance\consentguard.db)
.\.venv\Scripts\flask.exe --app wsgi seed-demo         # synthetic demo data; note ivy's TOTP secret it prints
.\.venv\Scripts\python.exe wsgi.py                     # API on http://127.0.0.1:5000

# 3. Frontend (second PowerShell window)
cd frontend
npm install
npm run dev                                            # UI on http://127.0.0.1:5173
```

Open **http://127.0.0.1:5173**. Alternatively run `npm run build` once; Flask then serves the built UI at
http://127.0.0.1:5000 (single origin, full CSP).

If PowerShell blocks `Activate.ps1`, you do not need it: the commands above call the venv executables directly.

### Commands

| Purpose | Command (from the folder shown) |
| --- | --- |
| Backend tests | `backend> .\.venv\Scripts\python.exe -m pytest` |
| Frontend tests | `frontend> npm test` |
| Frontend production build | `frontend> npm run build` |
| Live smoke test (servers running) | `root> backend\.venv\Scripts\python.exe scripts\smoke_test.py --totp-secret <ivy secret>` |
| Current TOTP code for a secret | `root> backend\.venv\Scripts\python.exe scripts\totp.py <secret>` |
| Create an investigator | `backend> .\.venv\Scripts\flask.exe --app wsgi create-investigator` |
| Reset demo data (deletes all data!) | `backend> .\.venv\Scripts\flask.exe --app wsgi seed-demo --reset --yes` |
| Audit tamper demonstration | `root> backend\.venv\Scripts\python.exe scripts\tamper_demo.py modify` then `... restore` |
| Verify audit chain from the CLI | `backend> .\.venv\Scripts\flask.exe --app wsgi verify-chain` |
| Forensic case study (own database) | `root> backend\.venv\Scripts\python.exe scripts\case_study.py setup` – full steps in [docs/case-study.md](docs/case-study.md) |
| Independent evidence examiner | `root> backend\.venv\Scripts\python.exe -I scripts\forensic_examiner.py acquire\|verify\|compare\|carve\|timeline ...` |
| Check migrations match models | `backend> .\.venv\Scripts\flask.exe --app wsgi db check` |
| Dependency / static security scans | `backend> .\.venv\Scripts\pip-audit.exe -r requirements.txt` · `.\.venv\Scripts\bandit.exe -r app` · `frontend> npm audit` |

## 12. Configuration (environment variables)

| Variable | Default | Meaning |
| --- | --- | --- |
| `CG_ENV` | development | `production` makes cookies Secure by default |
| `CG_ENCRYPTION_KEY` | *(required)* | 32-byte URL-safe base64 AES key |
| `CG_ENCRYPTION_KEY_ID` | k1 | Stored with each ciphertext |
| `CG_DATABASE_URL` | sqlite:///instance/consentguard.db | Relative paths resolve from `backend/` |
| `CG_COOKIE_SECURE` | false (dev) | Set `true` when served over HTTPS; also enables HSTS |
| `CG_SESSION_IDLE_MINUTES` / `CG_SESSION_ABSOLUTE_HOURS` | 30 / 8 | Session lifetimes |
| `CG_REQUIRE_MFA_FOR_INVESTIGATORS` | true | Investigation APIs require enrolled + verified MFA |
| `CG_LOGIN_RATE_LIMIT` / `CG_MFA_RATE_LIMIT` | 5 per minute;30 per hour | Per IP and per account |
| `CG_ALLOWED_ORIGINS` | localhost:5173/5000 | Origins accepted on state-changing requests |

## 13. Demo accounts, MFA setup and testing

`seed-demo` creates (password for all: **`Demo-Password-2026!`**, synthetic, demo only):

| User | Role | Notes |
| --- | --- | --- |
| alice | subject | health/contact/financial records; consents to acme (research) and brightads (marketing, withdrawn) |
| bob | subject | health/location/contact records; analytics consent to acme that **expires ~2 minutes after seeding** |
| acme | processor | Acme Health Research |
| brightads | processor | BrightAds Marketing – generated denied, post-withdrawal and probing attempts |
| ivy | investigator | MFA enabled; TOTP secret printed by `seed-demo`; owns one seeded case |

**MFA testing:** sign in → *Account security* → *Set up MFA* → scan the QR code with Microsoft/Google Authenticator,
Aegis or 1Password (or type the shown key) → enter the 6-digit code → **save the recovery codes** → sign out and in
again; you will be asked for a code. Without a phone, run `scripts\totp.py <secret>` to print the current code.
A code that was already used is rejected (replay protection) – wait for the next 30-second code. Recovery codes work
once each.

## 14. Known limitations and future work

* Local hash chain is tamper-evident, not immutable (see §9). Future: signed checkpoints to external WORM storage.
* Single-process write lock: multiple server processes could contend; uniqueness constraints prevent forks but a
  losing request fails rather than retries. Future: database-level serialization (PostgreSQL advisory locks).
* SQLite and the in-memory rate-limit store suit a single local server only (limits reset on restart).
  Future: PostgreSQL and Redis.
* Key rotation is designed for (key ids) but not automated; no KMS/HSM.
* Usernames are revealed as "not available" during registration (inherent to username sign-up); login errors and
  timing are generic.
* No password-reset-by-email (no email collected, by design); no account lockout (rate limiting instead).
* A case is visible only to its lead investigator; there is no team sharing or supervisor role.
* Detection rules are simple thresholds; expect false positives/negatives.
* Expiry is applied lazily on read/decision (accurate for authorization; the `expired` event is timestamped when
  first observed, while `expired_at` records the real expiry time).
* Development servers (Flask, Vite) are for local use only and bind to 127.0.0.1. A production deployment needs a
  WSGI server, HTTPS, `CG_COOKIE_SECURE=true` and secret management.

## 15. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `KeyConfigurationError: CG_ENCRYPTION_KEY is not set` | Run `python scripts\setup_env.py` from the project root |
| `no such table` errors | Run `flask --app wsgi db upgrade` in `backend` |
| `seed-demo` says users exist | Use `seed-demo --reset --yes` (deletes all data) |
| UI says "Cannot reach the ConsentGuard server" | Start the backend (`python wsgi.py`); Vite proxies `/api` to 127.0.0.1:5000 |
| "Too many attempts" | Login/MFA rate limit (5/min); wait a minute. Restarting the backend also clears it |
| "Missing or invalid CSRF token" | Refresh the page (a new session issues a new token) |
| MFA code rejected | Check the PC/phone clock; each code works once; wait for the next code |
| Records fail to decrypt after changing `.env` | The key changed. Restore the old key or reset demo data |
| Investigator sent to Account security | Investigators must enable MFA first |
| `npm` warns about esbuild install scripts | Harmless with npm 11; the build works without approving it |
