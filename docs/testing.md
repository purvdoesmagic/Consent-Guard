# ConsentGuard – Test plan and results

All results below were produced by actually running the commands on 2026-10-17 (Windows 11, Python 3.12.5,
Node 24.21.0, npm 11.19.0).

## 1. Test strategy

| Level | Tooling | Isolation |
| --- | --- | --- |
| Backend unit + API integration | pytest, Flask test client | Fresh SQLite file in pytest `tmp_path` and a freshly generated key per test; rate limiting disabled except in dedicated tests; low Argon2 cost for speed |
| CLI | Flask CLI runner | Same isolated database |
| Frontend unit + integration | Vitest, Testing Library, jsdom | `fetch` mocked per test |
| Production build | `vite build` | — |
| Live end-to-end | `scripts/smoke_test.py` (stdlib HTTP) | Running servers + seeded dev database |
| Tamper detection (live) | `scripts/tamper_demo.py` + `flask verify-chain` | Dev database, restored afterwards |
| Dependency / static analysis | `npm audit`, `pip-audit`, `bandit` | — |

Tests never touch `backend/instance/consentguard.db` or `.env`.

## 2. Backend suite – `backend> .\.venv\Scripts\python.exe -m pytest`

**Result: 118 passed, 0 failed (≈40 s).**

| File | Tests | Covers |
| --- | --- | --- |
| test_health.py | 4 | Health, security headers, JSON 404, refuses to start without key |
| test_auth.py | 19 | Register/login, cookie flags, Argon2id hashing, token-hash storage, weak/duplicate passwords, no self-registered investigators, generic + logged failures, logout invalidation and cookie replay, idle and absolute expiry, CSRF missing token, foreign Origin, MFA enroll + login, pending session restrictions, TOTP replay, single-use recovery codes, token rotation after MFA, password change revokes other sessions, login and MFA rate limits (429) |
| test_consent.py | 10 | Create + history + audit, validation, duplicate active consent, subject-only creation, update categories/expiry, immutable purpose, withdraw + terminal transitions, lazy expiry, inclusive expiry boundary (−1 µs allowed, = expiry denied), append-only versions |
| test_authorization.py | 16 | Anonymous rejection on all protected areas, owner access, consent-based allow, no-consent generic denial, after-withdrawal, purpose mismatch, category mismatch, re-consent, export denied, user A→user B record, not-found ≡ forbidden, cross-user consent view/modify/withdraw, recipient read-only, processor listing scope, investigator cannot read plaintext, no ciphertext in listings |
| test_crypto.py | 15 | Round-trip, wrong key, modified ciphertext, modified nonce/AAD, key-id mismatch, 2000 unique nonces, 6 invalid-key cases, valid key, AAD binding to category, tampered record → safe 500 |
| test_audit.py | 19 | Genesis/linking, canonical JSON, empty chain, valid chain, modified event, modified details, deleted event, reordered events, invalid predecessor hash, fork blocked by UNIQUE constraint, inserted event, truncation via checkpoint, documented tail-truncation limitation, sensitive-key rejection, rollback writes nothing, 6×15 concurrent writers, scoped visibility, filters, verify requires investigator + MFA |
| test_detection.py | 14 | R1 threshold N−1/N, inclusive window (exactly W vs W+1 ms), per-actor grouping, separate bursts, merged windows + severity, R2, R3/R4/R5, R6 distinct-resource counting and reason filtering, R7 boundary and fingerprint grouping, configurable thresholds, empty input, real supporting event IDs |
| test_investigations.py | 12 | Case numbering + audit, non-investigators blocked, investigator without MFA blocked, other investigator blocked (logged), linking + idempotence + chronological timeline with consent history, unknown event IDs rejected, timeline filters, case indicators with real event IDs + threshold override/validation, global detection, notes/status workflow/re-open justification, PDF content (title, case number, indicators, conclusions, VALID, every linked event ID, no plaintext) and authorization, PDF determinism |
| test_dashboard_and_integration.py | 3 | Dashboard counts from real data incl. expiry over time, API error shapes (415/400/413), full journey: MFA login → record → consent → access → withdrawal → denial → case → indicators → verify → PDF → dashboard |
| test_cli.py | 2 | `seed-demo` data consistency, refuses reseed, `verify-chain` valid and tampered |
| test_forensic_case.py | 4 | Independent examiner agrees with the app's head hash; acquisition hashes + custody log + no overwrite; full chain rewrite passes the app's check but fails the examiner (anchor, dangling references, diff); carving recovers deleted events with self-consistent hashes; modified event and modified image detected |

Defects found and fixed during development (all verified by re-running the suite):
* Per-request `g` flags leaked between requests when an outer app context existed (session cookie of one test client
  set on another) → flags now reset in `before_request`.
* Test assumption errors (expected 403 vs correct 404 for cross-user PATCH; dashboard clock not patched; timezone
  assumption in a frontend test; a TOTP replay test that could flake across a 30-second boundary) → tests corrected.
* Forged-insertion test revealed that the UNIQUE `prev_hash` constraint blocks naive forks → added as its own test.

## 3. Frontend suite – `frontend> npm test`

**Result: 17 passed, 0 failed (4 files).**

| File | Tests | Covers |
| --- | --- | --- |
| api.test.js | 4 | CSRF header only on writes, ApiError code/request id, network error, query strings |
| format.test.js | 3 | UTC formatting, local→UTC conversion (timezone independent), labels |
| components.test.jsx | 4 | EventTable details/hash reveal and selection; IndicatorList empty state and "not proof" disclaimer |
| app.test.jsx | 6 | Anonymous redirect, login → dashboard stats, MFA routing, generic login error, role-restricted page, investigator without MFA → account security |

## 4. Production build – `frontend> npm run build`

**Result: success** – `dist/index.html` 0.58 kB, CSS 12.40 kB, JS 261.82 kB (79.43 kB gzip). Flask served the build
at http://127.0.0.1:5000 with the full CSP; deep links (`/consents/1`) return the SPA; encoded path-traversal attempts
did not expose `.env`.

## 5. Live end-to-end – `scripts/smoke_test.py --totp-secret <ivy secret>`

Run against the Vite dev server proxying to the running backend with seeded data. **Result: 21/21 checks passed**:
health, headers, anonymous 401, generic bad-password 401, subject login, CSRF rejection, scoped consents, metadata-only
listing, owner decrypt, live dashboard, processor allowed under consent, category denial, processor blocked from
cases, post-withdrawal denial, cross-user denial, **login rate limit (6th attempt → 429)**, investigator MFA challenge,
TOTP verification, chain verification, seeded case visible, PDF download.

(The first run reported 4 failures because the rate limiter correctly throttled the 6th login within a minute; the
script was changed to assert that 429 explicitly rather than weakening the limit.)

## 6. Live tamper detection – `scripts/tamper_demo.py` + `flask --app wsgi verify-chain`

| Step | Result |
| --- | --- |
| Before | VALID, 75 events |
| `modify` (denied → allowed on seq 71) | INVALID: `HASH_MISMATCH` seq 71 |
| `restore`, `delete` seq 71 | INVALID: `SEQUENCE_GAP` seq 72, `PREVIOUS_HASH_MISMATCH` seq 72 |
| `restore` | VALID, 75 events |

`seed-demo --reset --yes` was exercised against a temporary database (reset → reseed → VALID chain of 41 events).

## 7. Security scans

| Tool | Result | Action |
| --- | --- | --- |
| `npm audit` (initial) | 5 vulnerabilities: react-router ≤7.17 (moderate, open redirect / SSR deserialization), vitest/@vitest/mocker/tinypool (dev-only; 2 critical) | Upgraded to react-router-dom 7.18.4 and vitest 5.0.5; tests and build re-run |
| `npm audit` (after) | **0 vulnerabilities** | — |
| `pip-audit -r requirements.txt` | **No known vulnerabilities found** | — |
| `bandit -r app` | 0 high, 0 medium, 4 low | Triaged as non-issues: `"csrf_token": None` (false positive); documented synthetic demo password in `cli.py`; deliberately wrong password used to generate the failed-login demo burst; `xml.sax.saxutils.escape` used only to escape PDF text (no XML parsing) |

## 8. Not tested / limitations of testing

* **Visual/manual UI review in a browser: NOT TESTED by the developer tooling in this session** (no browser
  automation was connected). The UI is covered by component/integration tests and the production build; perform the
  manual walkthrough in `faculty-demo.md` before presenting.
* Real authenticator apps: TOTP verified with `pyotp` (RFC 6238); scanning the QR code with a phone should be done
  manually once.
* Multi-process deployments, load testing, and browser compatibility beyond the build target were not tested.
* No dynamic web scanner (e.g. OWASP ZAP) was run.
