# Forensic case study: did QuickLoans misuse Carol's data?

All people, companies and data in this case are fake. The case is part of the demo data (`seed.py`) and is run
from the **Forensics** page when logged in as **ivy**. The code is in `backend/forensics.py`.

## The complaint

Carol gave **QuickLoans** permission to use her **financial** and **contact** data for her loan
(purpose: `service`). Later she started getting marketing calls, so she withdrew her permission.
The calls continued, and she complained.

The investigator, Ivy, wants to answer:

1. What did QuickLoans try to see, before and after Carol withdrew permission?
2. Did QuickLoans get any of Carol's data after she said stop?
3. Can we trust the activity log?

## What the log shows (case "Carol's complaint against QuickLoans")

| Step | What QuickLoans did | Result |
| --- | --- | --- |
| 1 | Viewed Carol's credit file and contact details for `service` | Allowed (2) |
| 2 | Asked for her contact details for `marketing` | Blocked: wrong purpose |
| 3 | Asked for her location history | Blocked: data type not allowed |
| 4 | *Carol withdraws permission* | |
| 5 | Tried 4 more times to view her data | Blocked: permission withdrawn |
| 6 | Tried 3 of Dave's records (Dave never gave permission) | Blocked: no permission |

The alerts page also flags QuickLoans: many blocked attempts (R1), trying after withdrawal (R2) and the wrong
purpose or data type (R3).

## The investigation, step by step (Forensics page)

| Step | Action | Result |
| --- | --- | --- |
| 1 | Look at the case and the alerts | 11 attempts: 2 allowed, 9 blocked |
| 2 | **Save evidence copy** | The whole database is copied to `backend/instance/evidence/`, with its SHA-256 and the last log hash written down |
| 3 | **Simulate the cover-up** (demo) | An "insider" deletes QuickLoans' 9 blocked attempts directly in the database and recalculates every hash |
| 4 | **Check the log** | **VALID**: the app's own check is fooled |
| 5 | **Compare with the evidence copy** | ✔ copy unchanged, ✘ last hash no longer exists, ✘ 9 entries missing, listed one by one |
| 6 | **Restore copy** | The database goes back to the evidence copy, so the demo can be repeated |

## Conclusion

* **QuickLoans got no data after Carol withdrew permission.** Every later attempt was blocked.
* The calls most likely used the phone number QuickLoans had already seen **before** she withdrew
  (step 1). Our system can't see what a company does with data it already has.
* QuickLoans repeatedly tried to use data it was not allowed to, including a non-customer's data.
* **Someone tampered with the log** to hide this. The hash chain alone did not catch it, because every hash
  was recalculated. The evidence copy, with its last hash, did.

## Forensics ideas used

| Idea | Where in the project |
| --- | --- |
| Evidence preservation | Save evidence copy (a copy plus its SHA-256 fingerprint) |
| Integrity verification | Hash-chained log, and the comparison with the evidence copy |
| Timeline reconstruction | The case's log entries in time order |
| Anti-forensics (hiding evidence) | The simulated insider cover-up |
| Reporting | PDF report with the facts, the integrity result and the last hash |

## Lesson learned

A check inside a system can be fooled by someone who controls that system. Keeping a copy of the evidence,
or at least the last hash, **outside** the system is what makes tampering provable.
