# ConsentGuard

[![CI](https://github.com/purvdoesmagic/Consent-Guard/actions/workflows/ci.yml/badge.svg)](https://github.com/purvdoesmagic/Consent-Guard/actions/workflows/ci.yml)

A website that lets people control which companies can use their personal data, and keeps a log
that shows if anyone tampers with it. Made as a college project.

All data in this project is **fake sample data**. Do not enter real personal data.

## The problem

When you allow an app to use your data and later say "stop", how do you know it really stops?
And if a company misuses your data, how can anyone prove what happened?

## What it does

| Who | What they can do |
| --- | --- |
| **User** (data owner) | Add personal data (stored encrypted), give a company permission for a purpose, withdraw it, see who tried to view their data |
| **Company** | Ask to see a user's data for a purpose. It only gets the data if the user's permission allows it |
| **Investigator** | See alerts about suspicious activity, open cases, add log entries as evidence, write notes, download a PDF report |

### How a permission check works

When a company asks for a record, the server checks:

1. Did the user give this company permission?
2. Is the permission for the same purpose (e.g. "research")?
3. Is the permission still active (not withdrawn or expired), and does it cover this type of data (e.g. "health")?

If all answers are yes, the data is shown. Otherwise, the request is blocked. Either way, the attempt is saved
in the activity log. The code is in `backend/permissions.py`.

### A log that can't be secretly changed

Every log entry stores the SHA-256 hash of the entry before it, like links in a chain. If someone edits or
deletes an entry, the hashes stop matching and the **Check the log** button reports INVALID
(`backend/audit_log.py`).

Limitation: someone with direct database access who knows the method could recalculate every hash. That's why
the last hash is printed in every PDF report, so it can be kept somewhere else. The case study below shows this.

### Security features

| Feature | How |
| --- | --- |
| Passwords | Stored as hashes (Werkzeug), at least 8 characters |
| Two-step login | Optional 6-digit code from Google/Microsoft Authenticator (TOTP, `pyotp`) |
| Personal data | Encrypted with AES-256-GCM; the key lives in `.env`, not in the database |
| Sessions | Signed, HttpOnly cookie, logged out after 30 minutes |
| Wrong passwords | Login blocked for 5 minutes after 5 wrong attempts |
| Roles | Every API route checks the user's role on the server |

### Suspicious-activity alerts (`backend/detection.py`)

| Rule | Triggers when |
| --- | --- |
| R1 Many blocked attempts | 3 or more blocked requests by one company within 10 minutes |
| R2 After withdrawal | A company tries to view data after the user withdrew permission |
| R3 Wrong reason | A company asks for data for a purpose or data type that was not allowed |
| R4 Many wrong passwords | 5 or more failed logins on one account within 10 minutes |

Alerts are leads for the investigator, not proof.

## Technology

* **Backend:** Python 3.12, Flask, SQLAlchemy, SQLite
* **Frontend:** React 18 with Vite
* **Other:** cryptography (AES), pyotp + segno (two-step login and QR code), ReportLab (PDF)
* **Tests:** pytest (backend), Vitest (frontend), GitHub Actions

## Project structure

```
Consent-Guard/
├─ backend/
│  ├─ app.py            starts the server
│  ├─ config.py         settings
│  ├─ models.py         database tables
│  ├─ permissions.py    the permission check
│  ├─ audit_log.py      hash-chained activity log
│  ├─ encryption.py     AES encryption of personal data
│  ├─ detection.py      suspicious-activity rules
│  ├─ report.py         PDF report
│  ├─ seed.py           creates demo data
│  ├─ routes/           API: auth.py, data.py, investigator.py
│  └─ tests/            pytest tests
├─ frontend/src/
│  ├─ App.jsx           menu and pages
│  ├─ api.js            calls the backend
│  └─ pages/            Login, Consents, Records, ActivityLog, Alerts, Cases, ...
├─ scripts/
│  ├─ setup_env.py      creates the .env file with random keys
│  ├─ case_study.py     the Carol vs QuickLoans case study
│  └─ totp.py           prints the current 6-digit code (demo without a phone)
└─ docs/case-study.md
```

## How to run (Windows PowerShell)

You need **Python 3.12** and **Node.js 20 or newer**.

```powershell
# 1. Create the .env file with secret keys (run once, from the project folder)
python scripts\setup_env.py

# 2. Backend
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe seed.py      # demo data (deletes the old demo database)
.\.venv\Scripts\python.exe app.py       # server on http://127.0.0.1:5000

# 3. Frontend (in a second window)
cd frontend
npm install
npm run dev                             # website on http://127.0.0.1:5173
```

Demo accounts (password for all: `Demo-Password-2026!`):

| Account | Role |
| --- | --- |
| alice, bob | User |
| acme, brightads | Company |
| ivy | Investigator |

Things to try: log in as **brightads** and request Alice's data (blocked, because she withdrew permission).
Log in as **alice**, give a permission, then withdraw it. Log in as **ivy**, open **Alerts**, create a case and
download the PDF report.

## Tests

```powershell
cd backend;  .\.venv\Scripts\python.exe -m pytest     # 27 tests
cd frontend; npm test                                  # 5 tests
```

## Case study

`scripts/case_study.py` tells the story of Carol, who withdrew permission from QuickLoans but kept getting
marketing calls. Someone then secretly deletes QuickLoans' blocked attempts from the log. The app's own check is
fooled, but comparing with a saved copy proves the cover-up. See [docs/case-study.md](docs/case-study.md).

## Limitations and future work

* The hash chain can be rewritten by someone with full database access. Future work: store the last hash
  outside the app (e.g. a signed copy or a timestamping service).
* SQLite and the built-in Flask server are for running locally only. Putting it online would need HTTPS and a
  proper server.
* The detection rules are simple thresholds, so they can miss things or raise false alarms.
* There is no "forgot password" option.

## License

MIT License, see [LICENSE](LICENSE).
