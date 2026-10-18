# ConsentGuard: guide for presenting to the faculty

This guide explains what the website does, what to click and what to say. The full live demo takes about
**10–12 minutes**. The forensic case study (Part D) is the main forensics topic, so leave the most time for it.

---

## 1. The project in 30 seconds

> "When we allow an app to use our data and later say *stop*, we have no way to check that it really stopped.
> ConsentGuard is a website where users give companies permission to use their data **for a specific purpose**.
> Every time a company asks for data, the server checks that permission, and **every attempt is saved in a log
> that cannot be secretly changed**. An investigator can then use that log as **digital evidence**. Our case
> study shows how we caught someone who deleted log entries to hide a company's misuse."

---

## 2. Before you present (5 minutes earlier)

1. Double-click **`run.bat`** in the project folder. The website opens at http://127.0.0.1:5000.
   Keep the black window open while presenting.
2. If you have already practised the demo, reset the data first. In the `backend` folder, run
   `.\.venv\Scripts\python.exe seed.py`, then start `run.bat` again.
3. Zoom the browser to 110–125% (Ctrl and +) so the faculty can read it.
4. On the login page, use the **one-click demo buttons**. Every account uses the password `Demo-Password-2026!`.

| Account | Role | Used in |
| --- | --- | --- |
| alice | User | Part A |
| brightads | Company | Part B |
| ivy | Investigator | Parts C and D |
| carol, quickloans | User, Company | The case study story |

---

## 3. What each page does

### Every role

| Page | What it shows | What to say |
| --- | --- | --- |
| **Home** | Numbers for your account and shortcuts | "Each role sees a different dashboard." |
| **Activity log** | Every action saved by the system, with filters (All / Allowed / Blocked / Logins) and search | "Even blocked attempts are saved. Nobody can quietly try and fail." |
| **Check the log** button | Walks through the hash chain and says VALID or INVALID | "Each entry stores the hash of the one before it, so changes break the chain." |
| **Account** | Turn on two-step login (6-digit code from a phone app) | "Optional extra security, the same idea as Google Authenticator." |

### User (alice)

| Page | What you can do |
| --- | --- |
| **My data** | Add personal data (title, type, content). It is **encrypted** before it is saved. |
| **My permissions** | Give a company permission: choose the company, the **purpose** (e.g. research) and the **data types** (e.g. health), optionally with an end date. **Withdraw** it at any time. |

### Company (brightads, acme, quickloans)

| Page | What you can do |
| --- | --- |
| **Permissions given to us** | See which users gave you permission, for what, and if it is still active. |
| **Request data** | Choose a purpose, then click **Request** on a record. You get the data only if the user's permission allows it. Otherwise you see why it was blocked. |

### Investigator (ivy)

| Page | What you can do |
| --- | --- |
| **Forensics** | The case study, step by step (Part D). |
| **Alerts** | 4 rules find suspicious behaviour in the log. **Open a case for this** creates a case with those log entries. |
| **Cases** | A case collects log entries as evidence, plus notes. **Download PDF report** creates a report that includes the log check result and the last hash. |
| **All permissions** | Every permission in the system. The investigator **cannot** read personal data. |

---

## 4. The live demo, step by step

### Part A: the user controls their data (alice, 2 min)

1. Click **alice**. Point at the home page numbers.
2. **My data**: click **View** on "Blood test results".
   *Say:* "This is stored encrypted with AES-256. In the database it's unreadable without the key."
3. **My permissions**: show that Acme has permission for *research* on *health* data, and that BrightAds'
   permission is **withdrawn**.
4. Give a new permission: Company **BrightAds**, Purpose **marketing**, tick **contact**, then click
   **Give permission**. Then click **Withdraw** on it.
   *Say:* "Withdrawing takes effect immediately, and both actions are logged."
5. **Activity log**: click the **Blocked** filter. *Say:* "Alice can see every company that tried to see her
   data and was blocked."

### Part B: a company is blocked (brightads, 1–2 min)

1. Log out and click **brightads**. Open **Request data**.
2. Choose purpose **marketing** and click **Request** on Alice's "Contact details".
   It shows **Blocked: Permission was withdrawn**.
3. Choose **analytics** and request "Bank summary". It shows **Blocked: Wrong purpose**.
   *Say:* "The server asks 3 questions: Did she give permission? For this purpose? Is it still active and
   does it cover this data type? Any 'no' means blocked."

### Part C: the investigator (ivy, 2 min)

1. Log out and click **ivy**. Open **Alerts**.
   *Say:* "Four simple rules: many blocked attempts, trying after withdrawal, wrong purpose or data type, and
   many wrong passwords. An alert is a lead, not proof."
2. Open **Cases**, then *BrightAds kept trying after Alice withdrew permission*. Show the evidence table and notes.
3. Click **Download PDF report** and open it. Point at the **log integrity result** and the **last hash**.

### Part D: the forensic case study (ivy, 4–5 min)

Open **Forensics** (the first item in ivy's menu) and go through the steps from top to bottom.

| Step | Click | What happens | What to say |
| --- | --- | --- | --- |
| Story | (read the box) | Carol's complaint | "Carol withdrew permission from QuickLoans but kept getting marketing calls." |
| 1 | **Open Carol's case** | 11 QuickLoans attempts: 2 allowed, 9 blocked | "Before withdrawal it legally read her phone number. After withdrawal it tried 4 more times, plus 3 records of Dave, who never gave permission. All blocked." |
| 2 | **Save evidence copy** | Copy saved with SHA-256 fingerprint and last hash | "Like sealing evidence in a bag. This copy is kept outside the live system." |
| 3 | **Simulate the cover-up**, then OK | 9 entries secretly deleted | "Now I play an insider with database access. They delete QuickLoans' blocked attempts and **recalculate every hash**." |
| 4 | **Check the log** | **VALID**, fooled | "The normal check can't see it, because every hash was recalculated. This is the limitation of a hash chain on its own." |
| 5 | **Compare with copy** | ✘ last hash gone, ✘ 9 entries missing, with the list | "Comparing with the evidence copy shows exactly what was deleted: all 9 are QuickLoans' blocked attempts." |
| 6 | **Restore copy**, then OK | Database back to before the cover-up | "We can undo the demo from the evidence copy." |

**Conclusion to say out loud:**
> "QuickLoans got **no data** after Carol said stop. Every attempt was blocked. The calls most likely used the
> phone number it had already seen legally before she withdrew. But someone deleted exactly the evidence of
> QuickLoans' attempts. The hash chain alone was fooled. **Keeping evidence outside the system** proved it.
> That's the main forensics lesson of our project."

Forensics ideas you can name:
- **Evidence preservation:** take a copy before analysing, and record its hash (SHA-256).
- **Integrity verification:** hash chain, plus a comparison with the saved copy.
- **Timeline reconstruction:** the case's log entries show the order of events.
- **Anti-forensics:** the insider tried to hide evidence. We detected it.
- **Reporting:** the PDF report records facts, the integrity result and the last hash.

---

## 5. How it works (for "show us the code" questions)

| Feature | File | One-line explanation |
| --- | --- | --- |
| Permission check | `backend/permissions.py` | `check_permission()` asks the 3 questions and returns allowed/blocked plus a reason |
| Hash-chained log | `backend/audit_log.py` | `add_log()` stores `prev_hash` and `hash = SHA-256(entry + prev_hash)`; `verify_chain()` recomputes them |
| Encryption | `backend/encryption.py` | AES-256-GCM with a random nonce. The key is in `.env`, not the database |
| Alerts | `backend/detection.py` | 4 rules (R1–R4) over the log entries |
| Forensics | `backend/forensics.py` | `save_copy()`, `compare()`, `restore()`, and the demo `simulate_cover_up()` |
| PDF report | `backend/report.py` | Built with ReportLab |
| Login and two-step | `backend/routes/auth.py` | Hashed passwords, TOTP codes, lockout after 5 wrong passwords |
| Website | `frontend/src/pages/` | One React file per page |

Tests: `backend` has 30 pytest tests and `frontend` has 6 Vitest tests. They run automatically on GitHub
(Actions).

---

## 6. Questions the faculty may ask

| Question | Answer |
| --- | --- |
| Why log blocked attempts too? | They show intent. In the case study, the blocked attempts were the evidence. |
| What is a hash chain? | Each entry stores the SHA-256 hash of the previous entry. Changing or deleting one entry breaks every link after it. |
| If the hash chain can be fooled, why use it? | It catches simple edits immediately. For an insider who recalculates everything, you also need an outside copy or the last hash, which is what step 5 shows. |
| How do you know the evidence copy wasn't changed? | We recorded its SHA-256 when we saved it. Step 5 checks it again ("evidence copy unchanged ✔"). |
| Can the investigator read personal data? | No. The permission check only allows the owner or a company with permission. |
| Where is the encryption key? | In the `.env` file on the server, never in the database. Without it, the data can't be read. |
| What does AES-GCM add? | Encryption plus a tamper check: a changed ciphertext fails to decrypt. |
| What happens when permission expires? | Before every check, the server marks expired permissions as expired, so access is blocked from that moment. |
| Is the data real? | No, everything is fake sample data. |
| What would you improve? | Store the last hash somewhere outside the app automatically (signed or timestamped), host it online with HTTPS, and use smarter detection. |
| Why SQLite? | It's simple and needs no installation, which is enough for a local project. A real deployment would use PostgreSQL. |

---

## 7. If something goes wrong

| Problem | Fix |
| --- | --- |
| "Cannot reach the server" | `run.bat` was closed. Start it again. |
| Login says "Too many wrong attempts" | Wait 5 minutes, or reset with `seed.py`. |
| The demo data looks messy after practice | Close `run.bat`, run `seed.py` in `backend`, then start `run.bat` again. |
| The cover-up says "Nothing to delete" | It was already done. Click **Restore copy**, or reset with `seed.py`. |
| Bob's permission shows "expired" | That's intended: it expires 2 minutes after seeding, to show expiry. |
