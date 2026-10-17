# Forensic case study CG-2026-0001 – Access after consent withdrawal and an insider log cover-up

All people, organisations and data are **synthetic**. Every output quoted below was produced by actually running
the commands on 2026-10-17; hashes and event IDs differ on each fresh run.

| | |
| --- | --- |
| Case | CG-2026-0001 |
| Complainant | `carol` (data subject) |
| Party complained about | `quickloans` – QuickLoans Credit Ltd (processor) |
| Also affected | `dave` (data subject, no relationship with QuickLoans) |
| Investigator | `ivy` (investigator, MFA enrolled) |
| Methodology | NIST SP 800-86 phases (collection → examination → analysis → reporting); ACPO principles 1–4 |
| Tools | ConsentGuard investigator UI, `scripts/forensic_examiner.py` (independent, stdlib-only) |

## 1. Background and complaint

Carol gave QuickLoans consent to process her **financial** and **contact** data for **service delivery** (her loan
application). She later started receiving **marketing calls**, withdrew her consent in ConsentGuard, and complained
that the calls continued. She asks: *did QuickLoans use my data after I withdrew consent?*

During the investigation a second problem appears: someone with database access **altered the audit log** to hide
QuickLoans' activity – and the application's own integrity check reported the altered log as VALID.

### Questions the investigation must answer
1. What did QuickLoans access, or try to access, before and after Carol's withdrawal?
2. Did QuickLoans actually obtain Carol's data after withdrawal?
3. Were other data subjects targeted?
4. Is the audit evidence intact? If not, what was changed, when, and can the original be recovered?

## 2. Reproducing the case

From the project root (PowerShell). The case uses its **own** database, `backend\instance\case_study.db`; the demo
database is not touched.

```powershell
$py = "backend\.venv\Scripts\python.exe"
& $py scripts\case_study.py setup --reset            # stage incident, open case, record a checkpoint
& $py -I scripts\forensic_examiner.py acquire --db backend\instance\case_study.db --out evidence\E1 --examiner ivy --note "Preservation after complaint"
& $py -I scripts\forensic_examiner.py verify evidence\E1 --examiner ivy
& $py scripts\case_study.py cover-up                 # the insider acts
& $py scripts\case_study.py app-verify               # application check: VALID (fooled)
& $py -I scripts\forensic_examiner.py acquire --db backend\instance\case_study.db --out evidence\E2 --examiner ivy --note "Re-acquisition before report"
& $py -I scripts\forensic_examiner.py verify evidence\E2 --anchor evidence\E1 --examiner ivy
& $py -I scripts\forensic_examiner.py compare evidence\E1 evidence\E2 --examiner ivy
& $py -I scripts\forensic_examiner.py carve evidence\E2 --out evidence\E2_carved.json --examiner ivy
& $py -I scripts\forensic_examiner.py timeline evidence\E1 --out evidence\E1_timeline.csv --examiner ivy
```

To run it again, first delete the old evidence (`Remove-Item -Recurse -Force evidence`); the examiner refuses to
overwrite an evidence folder.

To view the case in the UI (before the cover-up, to see detection rules R1–R6 fire on the full evidence):

```powershell
cd backend
$env:CG_DATABASE_URL = "sqlite:///instance/case_study.db"; .\.venv\Scripts\python.exe wsgi.py
# second window: cd frontend; npm run dev  ->  sign in as ivy, TOTP from scripts\totp.py <secret printed by setup>
```

The scenario is scripted, so all events fall within about one second. Real incidents span days; the analysis is
the same.

## 3. Collection (preservation and acquisition)

**ACPO principle 1 – do not change the original.** The examiner never opens the live database for writing. It takes a
bit-for-bit copy, hashes the source **before and after** copying and the image itself, and accepts the copy only if
all three SHA-256 values match. It refuses to acquire while a SQLite `-journal`/`-wal` file exists (a write in
progress). The image is then marked read-only and is only ever opened with SQLite `mode=ro&immutable=1`.

**Evidence register**

| Item | Acquired (UTC) | Purpose | Image SHA-256 | Chain head (anchor) |
| --- | --- | --- | --- | --- |
| E1 | 2026-10-17T08:00:17Z | Preservation right after the complaint | `42e028fb73a9a30c0b9ba7ec7628f3d9fb1a42100a8e664c0b0f9931d208320d` | seq 31, `6b56bdbcb8e288f84f250c2da330c872ba8bb09acb41d459eed2a356791fe8a2` |
| E2 | 2026-10-17T08:00:28Z | Re-acquisition before reporting | `55e3c1bc47e69b1a3835a166bf3545d5a024287dfa64fb8ba0568837a1fb4a59` | seq 22, `5e5e7a87e21d7392b40af18078abe2739ece35cf0fd79a0ca35bd0a300bfc527` |

**Anchor.** At acquisition the E1 chain head (seq 31 + hash) was written to the manifest. That anchor is the
investigator's own copy of the log's state, held **outside** ConsentGuard, the same role as the head hash printed in
every PDF report. In practice it would also be emailed or printed and signed.

**Chain of custody.** Every examiner action appends an entry to `manifest.json`, with a fresh hash of the image.
E1's log after the examination:

```
acquired           2026-10-17T08:00:17Z  ivy  image 42e028fb…
verified           2026-10-17T08:00:17Z  ivy  image 42e028fb…  problems 0
compared (with E2) 2026-10-17T08:00:28Z  ivy
timeline_exported  2026-10-17T08:00:28Z  ivy  rows 33
```

**Tool validation (ACPO principle 3 – a third party must be able to repeat the work).** The examiner re-implements the
hash chain from the published algorithm (README §9) without importing any ConsentGuard code. On E1 it produced the
same head hash as the application (`6b56bdbc…`), so the two independent implementations agree. The automated tests
in `backend/tests/test_forensic_case.py` check this on every run.

## 4. Examination

### 4.1 The application's view after the cover-up

```
> case_study.py app-verify
Application verify_chain(): VALID - 22 events, head seq 22 5e5e7a87e21d…
```

The insider deleted 9 events, renumbered the remaining ones, recomputed every following hash and rewrote the stored
checkpoint to match. To the application, the log looks clean. This is the limitation documented in README §9:
the chain is **tamper-evident, not tamper-proof**, against someone with database access who knows the algorithm.

### 4.2 Independent verification of E2 against the E1 anchor

```
[OK]   Evidence integrity: image SHA-256 matches acquisition hash
[OK]   Internal hash chain: 22 events, head seq 22
[FAIL] Cross-references: 9 linked event ID(s) missing
       event seq 21 references missing event 4684edd0-7530-4596-8455-2e45a49387b2
       … (9 IDs in total)
[FAIL] External anchor from E1: anchor head seq 31 no longer exists: the chain held 31 events
       when anchored and now holds 22 (events removed and chain rewritten or truncated)
RESULT: 2 CHECK(S) FAILED
```

The tampering is caught by two independent signals:
* **External anchor.** The log ivy preserved had 31 events with head `6b56bdbc…`; that state no longer exists.
* **Internal cross-reference.** Event seq 21 (`case.events_linked`, written when ivy opened the case) lists the
  evidence IDs she linked. Nine of them no longer exist. The insider rewrote the hashes but missed this reference.

### 4.3 What changed: diff E1 → E2

```
Comparing E1 (31 events) -> E2 (22 events)
  Removed events      : 9
    seq 19  08:00:14.640842Z  record.access  quickloans  denied DENY_PURPOSE_NOT_COVERED
    seq 20  08:00:14.649850Z  record.access  quickloans  denied DENY_CATEGORY_NOT_COVERED
    seq 22  08:00:14.676983Z  record.access  quickloans  denied DENY_CONSENT_WITHDRAWN
    seq 23  08:00:14.685982Z  record.access  quickloans  denied DENY_CONSENT_WITHDRAWN
    seq 24  08:00:14.698993Z  record.access  quickloans  denied DENY_CONSENT_WITHDRAWN
    seq 25  08:00:14.713086Z  record.access  quickloans  denied DENY_CONSENT_WITHDRAWN
    seq 26  08:00:14.727088Z  record.access  quickloans  denied DENY_NO_CONSENT
    seq 27  08:00:14.738254Z  record.access  quickloans  denied DENY_NO_CONSENT
    seq 28  08:00:14.750777Z  record.access  quickloans  denied DENY_NO_CONSENT
  Altered content     : 0
  Renumbered (seq)    : 4
  Re-hashed           : 4  (a changed hash on unchanged content = chain recomputed)
  Added (newer only)  : 0
```

The removal is **selective**: every removed event is a *denied* access attempt by QuickLoans. Its allowed accesses,
and everyone else's events, were left in place. "Re-hashed with unchanged content" is the fingerprint of a deliberate
chain recomputation, not of corruption.

### 4.4 Recovery without the earlier image: SQLite record carving

What if E1 had not been taken? SQLite does not wipe deleted rows (`secure_delete` is off in this build). It only
overwrites the first 4 bytes of a freed cell, which destroys the payload length, rowid and header-size byte but leaves
the column type list and the values. The examiner finds every event UUID in the raw file, searches backwards for a
type list that puts a 36-byte text exactly at the `event_id` column, and decodes the row.

```
Carved evidence.db: 184320 bytes, 0 free page(s), 31 audit record(s) found in raw bytes
  Deleted records recovered (not in live table): 9
    orig seq 19 … DENY_PURPOSE_NOT_COVERED   hash self-consistent: YES
    orig seq 20 … DENY_CATEGORY_NOT_COVERED  hash self-consistent: YES
    orig seq 22 … DENY_CONSENT_WITHDRAWN     hash self-consistent: YES
    … (all 9 recovered, all YES)
  Superseded versions of live records: 1
```

All 9 deleted events were recovered **from the tampered image E2 alone**. "Self-consistent" means that recomputing
each recovered row's SHA-256 gives exactly the hash stored in it, so the bytes are the original record written by the
application and not something reconstructed or fabricated. The recovered IDs are the same 9 IDs found by the
cross-reference check and the diff, so three independent methods agree.

## 5. Analysis: reconstructed timeline (from E1, confirmed by carving)

| Seq | Time (UTC) | Event | Outcome / reason | Purpose · category | Interpretation |
| --- | --- | --- | --- | --- | --- |
| 16 | 08:00:14.592 | Carol grants consent #1 to QuickLoans | – | service_delivery · financial, contact | Lawful basis starts |
| 17 | 08:00:14.621 | QuickLoans reads Carol's credit file | **allowed**, ALLOW_CONSENT | service_delivery · financial | Legitimate |
| 18 | 08:00:14.631 | QuickLoans reads Carol's contact card | **allowed**, ALLOW_CONSENT | service_delivery · contact | Legitimate; QuickLoans now **has** her phone number |
| 19 | 08:00:14.640 | QuickLoans requests contact card | denied, PURPOSE_NOT_COVERED | **marketing** · contact | Function creep: tries to use it for marketing (R4) |
| 20 | 08:00:14.649 | QuickLoans requests location history | denied, CATEGORY_NOT_COVERED | service_delivery · **location** | Asks for data never consented (R5) |
| 21 | 08:00:14.662 | **Carol withdraws consent #1** | – | – | Lawful basis ends |
| 22–25 | 08:00:14.676–.713 | 4 × access to Carol's contact/financial | denied, CONSENT_WITHDRAWN | service_delivery | Continued attempts after withdrawal (R2; R1 burst) |
| 26–28 | 08:00:14.727–.750 | Dave's credit, contact, health records | denied, NO_CONSENT | marketing | Probing a non-customer, 3 distinct records (R6) |
| 29–31 | 08:00:14.766–.885 | ivy opens case, links evidence, verifies chain | – | – | Investigation begins; E1 acquired |
| – | between 08:00:17 and 08:00:28 | 9 events deleted, chain re-hashed, checkpoint rewritten | – | – | Anti-forensics (not logged by the application) |

## 6. Findings

Findings are kept separate from conclusions, as in the PDF report.

**F1 – Legitimate access before withdrawal.** QuickLoans read Carol's financial and contact records under consent #1
(seq 17, 18). This access was lawful.

**F2 – Attempted use outside the consented purpose and scope.** Before the withdrawal, QuickLoans asked for Carol's
contact data for *marketing* (seq 19) and for her *location* data (seq 20). Both were denied by ConsentGuard.

**F3 – Continued attempts after withdrawal.** After the withdrawal at seq 21, QuickLoans made 4 further access
attempts on Carol's records (seq 22–25). All were **denied**; ConsentGuard released no data after withdrawal.

**F4 – Other subjects targeted.** QuickLoans requested 3 records belonging to Dave, with whom it has no consent
relationship, for marketing (seq 26–28). All were denied. This pattern matches enumeration (R6).

**F5 – The audit log was altered after the case was opened.** Between E1 (08:00:17Z) and E2 (08:00:28Z), the 9 denied
QuickLoans events (seq 19, 20, 22–28) were deleted, the remaining events renumbered and re-hashed, and the stored
checkpoint rewritten. Shown by: the E1 anchor mismatch, 9 dangling evidence references, the E1→E2 diff, and carving
of the original rows from E2 itself.

**F6 – The original evidence is recoverable and authentic.** All 9 removed events exist unaltered in E1, and were
independently carved from E2 with self-consistent hashes.

## 7. Conclusions

1. **Answer to Carol's question:** ConsentGuard did **not** give QuickLoans any of Carol's data after she withdrew
   consent (F3). However, QuickLoans had already obtained her contact number lawfully at seq 18 (F1), and tried to
   use it for marketing (F2). The marketing calls are therefore consistent with QuickLoans **retaining and reusing
   data it obtained before withdrawal**. ConsentGuard's logs cannot show what QuickLoans did with data inside its own
   systems; that requires QuickLoans' records (call logs, CRM exports), obtained through the appropriate legal or
   regulatory route.
2. QuickLoans repeatedly tried to process personal data outside its consent: wrong purpose, wrong category, after
   withdrawal, and for a non-customer (F2–F4). This is a pattern, not a one-off error.
3. A separate incident occurred: **someone with direct database access removed exactly the evidence that
   incriminated QuickLoans** (F5). The application has no record of who did it, because the change bypassed the
   application. Next steps: review database-server access logs, OS logon events and file-system timestamps for
   `case_study.db` between 08:00:17Z and 08:00:28Z, and interview staff with database access.
4. The investigation can rely on E1 and the carved records (F6). E2 should be retained as evidence of the tampering
   itself.

## 8. Lessons and recommendations

| Observation | Recommendation |
| --- | --- |
| An insider who knows the algorithm can produce a chain the application accepts as VALID | Anchor the head hash **outside** the system: signed checkpoints, WORM storage, an RFC 3161 timestamping authority, or at least the PDF report's head hash filed elsewhere |
| Preserving E1 immediately after the complaint is what made the cover-up provable | Make "acquire and hash first" the first step of every case; automate periodic acquisitions |
| Deleted SQLite rows were carved from free space | Positive for investigators. Note also that a careful attacker could run `VACUUM` (or enable `secure_delete`) to destroy residue, so carving must not be the only control |
| The insider missed the IDs inside `case.events_linked` | Redundant references help, but a careful attacker could fix those too; only external anchors are robust |
| The application logs nothing about direct DB edits | Restrict and monitor DB access separately (DB audit logs, OS file auditing); separate the duties of DB admins and investigators |

## 9. Limitations of this case study

* Synthetic, compressed timeline (about 1 s); real incidents would also need clock-skew analysis.
* Acquisition is a logical file copy of a quiescent SQLite database, not a disk image; file-system slack and
  deleted rollback journals were not examined.
* Carving depends on `secure_delete` being off and no `VACUUM` having run since the deletion.
* Attribution of the cover-up to a person needs evidence outside ConsentGuard (§7.3).

## 10. Viva questions this case answers

| Question | Short answer |
| --- | --- |
| If the hash chain can be rewritten, what is it good for? | It forces the attacker to rewrite **everything after** the change, which an external anchor exposes immediately |
| Why an independent tool rather than the app's own verify? | The app's code and data are what is under investigation; an independent implementation that gives the same result validates both |
| How do you know the carved rows are real? | Each carved row's recomputed SHA-256 equals the hash stored inside it, and they match the earlier image E1 |
| Why are the images read-only and opened `immutable`? | ACPO principle 1: examination must not change the evidence; custody entries re-hash the image each time |
| Did QuickLoans get Carol's data after withdrawal? | No – every post-withdrawal request was denied. It reused data it had already obtained |
