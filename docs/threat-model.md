# ConsentGuard – Threat model and security controls

## 1. Assets

| Asset | Why it matters |
| --- | --- |
| Protected record payloads | Sensitive (synthetic) personal data |
| Consent state and history | Determines legal basis for access |
| Audit trail | Evidence for accountability and investigations |
| Credentials, session tokens, MFA secrets, recovery codes | Account takeover |
| Encryption key | Decrypts all records and MFA secrets |
| Investigation cases, notes and reports | Confidential findings |

## 2. Actors and trust boundaries

* **Anonymous internet user** – can reach public endpoints (health, session, register, login).
* **Data subject** – owns records and consents.
* **Processor** – may read data only under active, matching consent; may try to over-reach.
* **Investigator** – sees all events and consent metadata, never plaintext records; MFA mandatory.
* **Insider with database access** – can edit SQLite directly (bypasses the application).
* **Insider with server access** – can read `.env` and run code.

Boundaries: browser ↔ API (untrusted input), API ↔ database, application ↔ key material (environment).

## 3. Threats (STRIDE) and controls

| Threat | Example | Controls | Residual risk |
| --- | --- | --- | --- |
| **Spoofing** | Password guessing, credential stuffing | Argon2id; password policy; rate limits per IP and per account on login/MFA; generic errors; dummy hash for unknown users; TOTP MFA; investigators must use MFA | In-memory limiter resets on restart; no breached-password API |
| Spoofing | Session theft / fixation | 256-bit random token, only SHA-256 stored; HttpOnly, SameSite=Strict, Secure (configurable); rotation at login and after MFA; idle 30 min / absolute 8 h; logout and password change revoke | HTTP in dev means no Secure flag locally |
| Spoofing | TOTP replay | Last used time-step stored; code at/before it rejected | Phishing of a fresh code (real-time relay) |
| **Tampering** | CSRF on state-changing endpoints | Synchronizer token per session (constant-time compare); Origin allow-list; JSON-only bodies (415 otherwise); SameSite=Strict | — |
| Tampering | Editing audit rows in the DB | SHA-256 hash chain; UNIQUE seq/prev_hash; verification findings; checkpoints; head hash in PDF reports | Full rewrite of chain + checkpoints by a DB+code-aware insider is undetectable locally |
| Tampering | Swapping ciphertext between records or changing category metadata | AES-GCM AAD binds record id, owner and category | — |
| Tampering | SQL injection | SQLAlchemy ORM/parameters only; LIKE wildcards escaped | — |
| **Repudiation** | "I never accessed that record" | Every access decision logged with actor, consent, reason, request id; logs hash-chained | Logs prove what the app observed, not intent |
| **Information disclosure** | IDOR on records/consents/cases | Ownership/role checks in services; not-found and forbidden are indistinguishable (403 `ACCESS_DENIED` / 404); denials logged | — |
| Information disclosure | Plaintext/secrets in logs | Audit details reject sensitive keys; payloads never logged; generic 500s; MFA secrets encrypted | Server stdout shows request lines (no bodies) |
| Information disclosure | XSS | React escaping; no `dangerouslySetInnerHTML`; strict CSP (`script-src 'self'`, no inline); PDF text escaped | — |
| Information disclosure | Clickjacking / sniffing | `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`, COOP/CORP | — |
| Information disclosure | Key exposure | Key only in `.env` (git-ignored); fail-closed validation; never logged or returned | Anyone with server file access can read `.env` (no KMS) |
| Information disclosure | Username enumeration | Generic login errors and timing; registration necessarily reveals taken usernames | Registration endpoint rate-limited only |
| **Denial of service** | Request flooding, huge bodies | `MAX_CONTENT_LENGTH` 64 KiB; rate limits on auth; paging limits (≤200) and detection cap (5000 events) | Dev server is not hardened; local deployment only |
| **Elevation of privilege** | Self-registering as investigator | Registration accepts only subject/processor; investigators via CLI | — |
| Elevation of privilege | Bypassing UI restrictions via direct API calls | Every protected endpoint enforces roles and resource checks server-side; tests call the API directly | — |
| Elevation of privilege | Access after withdrawal/expiry | Lazy expiry refresh before every decision; withdrawn/expired never authorize; terminal states | — |

## 4. Security headers

`Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src
'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'` ·
`X-Content-Type-Options: nosniff` · `X-Frame-Options: DENY` · `Referrer-Policy: no-referrer` ·
`Cross-Origin-Opener-Policy: same-origin` · `Cross-Origin-Resource-Policy: same-origin` ·
`Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()` · `Cache-Control: no-store` (API) ·
`Strict-Transport-Security` when `CG_COOKIE_SECURE=true`.

## 5. Audit integrity: precise guarantees

Proves: stored events match their hashes; each links to its predecessor; the last checkpointed head still exists
unchanged. Detects: modified fields, deleted events, events inserted or reordered mid-chain, forks (blocked by
UNIQUE constraints), truncation behind a checkpoint.

Does not prove: absence of a complete rewrite by someone controlling both the database and the algorithm; absence
of tail truncation after the last checkpoint; truthfulness of what the application recorded.

Stronger options (not implemented): periodically sign the head hash with a key kept off the server; publish signed
checkpoints to an independent append-only service (WORM bucket with object lock, transparency log, RFC 3161
timestamping authority); replicate events to a separately administered log server.

## 6. Out of scope / accepted risks

Production TLS termination, WAF, centralised logging, KMS/HSM, backups, multi-process rate-limit storage,
account recovery without MFA codes, and protection against a fully compromised server.
