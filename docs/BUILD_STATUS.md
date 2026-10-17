# Build status

Last updated: 2026-10-17.

## Phases

| Phase | Status |
| --- | --- |
| 1. Workspace, skeleton, config, database foundation, health endpoint | Complete |
| 2. Authentication, sessions, MFA, security middleware | Complete |
| 3. Consent lifecycle, protected records, authorization | Complete |
| 4. Encryption, structured access-event logging | Complete |
| 5. Audit hash chain and verification | Complete |
| 6. Investigations, timelines, detection rules, PDF reports | Complete |
| 7. React interface integrated with the real API | Complete |
| 8. Full test runs, production build, security scans | Complete |
| 9. Documentation, cleanup, faculty demo preparation | Complete |

## Latest verified results

* Backend: `pytest` → 118 passed (incl. 4 forensic case-study tests)
* Forensic case study (docs/case-study.md): cover-up passes the app's check, detected by the examiner, 9/9 deleted events carved
* Frontend: `npm test` → 17 passed; `npm run build` → success
* Live smoke test (Vite proxy + seeded data) → 21/21
* Live tamper demo → detected (modify, delete), VALID after restore
* `npm audit` → 0 vulnerabilities (after upgrading react-router-dom and vitest); `pip-audit` → none; `bandit` → 4 low, triaged
* `flask db check` → no pending schema changes

## Open items

* Manual visual walkthrough of the UI in a browser: partly done (investigator password + TOTP login, dashboard and
  case page checked in Chrome against the case-study database, no console errors). Subject and processor screens
  still need a manual pass before the demo.
* Optional future work listed in README §14.
