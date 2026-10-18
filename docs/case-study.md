# Case study: did QuickLoans misuse Carol's data?

All people, companies and data in this case are fake.

## The story

Carol gave **QuickLoans** permission to use her **financial** and **contact** data for her loan
(purpose: `service`). Later she started getting marketing calls, so she withdrew her permission.
The calls continued, and she complained.

The investigator, Ivy, wants to answer:

1. What did QuickLoans try to see, before and after Carol withdrew permission?
2. Did QuickLoans get any of Carol's data after she said stop?
3. Can we trust the activity log?

## Running it

From the project folder (it uses its own database, `backend\instance\case_study.db`):

```powershell
$py = "backend\.venv\Scripts\python.exe"
& $py scripts\case_study.py setup       # create the story
& $py scripts\case_study.py save-copy   # Ivy saves a copy of the database as evidence
& $py scripts\case_study.py cover-up    # someone secretly edits the log
& $py scripts\case_study.py check       # check the log in two ways
```

## What happened (from the log)

| Step | What QuickLoans did | Result |
| --- | --- | --- |
| 1 | Viewed Carol's credit file and contact details for `service` | Allowed |
| 2 | Asked for her contact details for `marketing` | Blocked: wrong purpose |
| 3 | Asked for her location history | Blocked: data type not allowed |
| 4 | *Carol withdraws permission* | |
| 5 | Tried 4 more times to view her data | Blocked: permission withdrawn |
| 6 | Tried 3 of Dave's records (Dave never gave permission) | Blocked: no permission |

Ivy opens a case and saves a copy of the database (24 log entries).

## The cover-up

Someone with direct access to the database deletes QuickLoans' 9 blocked attempts. Then they recalculate
every hash so the chain looks correct again. 15 entries are left.

## Checking the log

```
1) The app's own check: VALID (15 entries)
   -> The app was fooled, because every hash was recalculated.
2) Compare with the saved copy:
   Saved copy unchanged since it was saved: YES
   FAIL: the copy had 24 entries ending with hash 42d1e4e6...,
         but now there are 15 entries and that hash no longer exists.
   Entries missing compared to the copy: 9
```

The comparison lists exactly which 9 entries were deleted: all of them are QuickLoans' blocked attempts.

## Conclusion

* **QuickLoans got no data after Carol withdrew permission.** Every later attempt was blocked.
* The calls most likely used the phone number QuickLoans had already seen **before** she withdrew
  (step 1). Our system can't see what a company does with data it already has.
* QuickLoans repeatedly tried to use data it was not allowed to, including a non-customer's data.
* **Someone tampered with the log** to hide this. The hash chain alone did not catch it, but the saved copy
  and its last hash did.

## Lesson learned

A check inside a system can be fooled by someone who controls that system. Keeping a copy of the evidence,
or at least the last hash, **outside** the system is what makes tampering provable.
