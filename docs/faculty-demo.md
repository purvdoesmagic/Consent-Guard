# ConsentGuard – Faculty demonstration guide

Duration: about 20–25 minutes. All data is synthetic.

## Before the session (10 minutes, the day before)

- [ ] `python scripts\setup_env.py` (keeps an existing key)
- [ ] `cd backend` → `.\.venv\Scripts\python.exe -m pytest` → expect **118 passed**
- [ ] `cd frontend` → `npm test` → expect **17 passed**; `npm run build` succeeds
- [ ] Fresh data: `.\.venv\Scripts\flask.exe --app wsgi seed-demo --reset --yes` — **copy ivy's TOTP secret**
- [ ] Add the secret to an authenticator app (or plan to use `scripts\totp.py <secret>`)
- [ ] Start backend (`python wsgi.py`) and frontend (`npm run dev`); open http://127.0.0.1:5173
- [ ] Walk through the steps below once in a browser (this visual check has not been automated)
- [ ] Have `docs/architecture.md` and `docs/threat-model.md` open for questions

**Tips:** Use separate browser profiles or private windows for alice, brightads/acme and ivy, so you sign in only
once per user. Login is rate limited to 5 attempts per minute per IP; if you see "Too many attempts", wait a
minute (this is itself a demonstrable control). Bob's analytics consent expires ~2 minutes after seeding, so by demo
time it is expired.

## Demo script

### 1. Problem and architecture (3 min)
Explain: consent separated from access control and mutable logs make privacy complaints hard to investigate.
Show the architecture diagram in `docs/architecture.md`: React → Flask API → services (authorization, consent,
audit chain, investigations) → SQLite; key in `.env`.

### 2. Subject view – consent lifecycle (5 min) – sign in as **alice** / `Demo-Password-2026!`
1. **Dashboard**: live counts (active/withdrawn/expired consents, access attempts, denied attempts), integrity VALID,
   recent activity with real actors.
2. **My consents**: two active (acme research, health+demographic) and one withdrawn (brightads marketing). Open the
   withdrawn one → history: created → withdrawn.
3. **New consent** → recipient *BrightAds Marketing*, purpose *Analytics*, category *Demographic*, expiry in 3 minutes.
   Show the version history. **Edit preferences** → add *Contact* → version 2.
4. Try to edit the withdrawn consent: there is no edit button, and the API returns 409 `INVALID_TRANSITION` (mention).
5. **My protected records** → *Decrypt & view* the blood panel (ALLOW_OWNER). Explain AES-256-GCM, nonce per
   encryption, AAD binding; ciphertext only in the database.
6. **Access history**: expand an event to show `prev_hash` and `hash`.

### 3. Processor view – backend enforcement (4 min) – sign in as **acme**
1. **Request data access**: pick Alice's *blood panel*, purpose *Medical research* → **allowed** (consent #).
2. Same record, purpose *Marketing* → **DENY_PURPOSE_NOT_COVERED**.
3. Alice's *bank summary*, *Medical research* → **DENY_CATEGORY_NOT_COVERED**.
4. Bob's *location history*, *Aggregated analytics* → **DENY_CONSENT_EXPIRED** (consent expired after seeding).
5. Paste a random 32-hex ID → generic **ACCESS_DENIED** (cannot probe which records exist).
6. Point out: hiding buttons is not security – every check happens in `services/authorization.py` and is logged.

Optional (as alice): withdraw the new BrightAds consent, then as brightads request Alice's contact card with
*Marketing* → **DENY_CONSENT_WITHDRAWN**.

### 4. Investigator view – forensics (6 min) – sign in as **ivy**, enter the TOTP code
1. Note the MFA step (investigators cannot use investigation features without MFA).
2. **Detection rules** → Run rules: R2 access after withdrawal, R1 repeated denials, R4/R5 mismatches, R6 broad
   probing of Bob's records, R7 failed-login burst against alice (and R3 after Bob's expiry). Each indicator explains
   the rule and lists supporting event IDs; stress "indicator, not proof".
3. **Cases** → open the seeded case → **Timeline**: access events merged with consent history (withdrawal visible
   before the denied attempts). Filter by outcome = denied.
4. **Indicators** tab: the case holds 8 denied BrightAds attempts; rerun with *Denials (R1)* = 10 → R1 disappears,
   set it back to 3 → it returns (configurable, boundary-tested).
5. **Notes & findings**: add a *conclusion*. Change status to *Under review*.
6. **Report** tab → download PDF. Walk through: observed facts vs indicators vs notes vs conclusions, event IDs,
   integrity result with chain head hash, limitations.

### 5. Tamper evidence (3 min)
1. **Integrity verification** → *Run verification & record checkpoint* → VALID.
2. In a terminal (project root): `backend\.venv\Scripts\python.exe scripts\tamper_demo.py modify` – changes a denied
   access event to "allowed" directly in SQLite (an insider covering tracks).
3. Run verification again → **HASH_MISMATCH** on that sequence number; dashboard shows integrity Invalid.
4. `scripts\tamper_demo.py restore` → verify → VALID. (Optionally `delete` → SEQUENCE_GAP + PREVIOUS_HASH_MISMATCH.)
5. Explain honestly what this proves and doesn't (see the right-hand panel): a full chain rewrite by someone with DB
   and code access is not detectable locally; the head hash in the PDF acts as an external checkpoint.

### 6. Account security and tests (2 min)
- **Account security** (as any user): MFA QR enrollment, recovery codes (shown once, single-use), active sessions,
  "sign out other sessions", password change revokes other sessions.
- Show `docs/testing.md`: 118 backend tests, 17 frontend tests, smoke test 21/21, dependency scans.

### 7. Forensic case study CG-2026-0001 (optional, 5 min)
Follow §2 of `docs/case-study.md`: acquire E1 → insider cover-up → the app says VALID → the independent examiner
shows the anchor mismatch, the E1→E2 diff and the 9 carved deleted events. This is the case assigned by the faculty.

## Likely questions

| Question | Answer pointer |
| --- | --- |
| Why can't the investigator read records? | Least privilege: investigation needs metadata and decisions, not content (rule 4 in authorization) |
| What if two requests write audit events at once? | Process lock + one transaction; UNIQUE seq/prev_hash prevents forks; concurrency test |
| What if the key is lost? | Records and MFA secrets are unrecoverable; back up `.env` separately (README §8) |
| Is the log immutable? | No – tamper-evident. External signed checkpoints would be the next step |
| Why lazy expiry? | Every decision refreshes expiry first, so an expired consent can never authorize; no background job needed |
| How are CSRF attacks prevented with cookies? | SameSite=Strict + per-session synchronizer token + Origin allow-list + JSON-only |

## Known limitations to state proactively
Local hash chain only; single-process lock; SQLite and in-memory rate limits; no automated key rotation/KMS; case
visible only to its lead investigator; rule thresholds are simple; development servers are not production servers.
