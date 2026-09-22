# Client B Onboarding — Reconciliation

## The Setup

Client B needed reconciliation between two internal systems that had never been compared programmatically: an internal ledger export and a custodian statement.

## First Contact With the Data

The two files looked nothing alike. Column names didn't match at all (`TransactionRef` vs `ref_id`, `Amt` vs `settlement_amount`), the date formats were different (`01/20/2026` vs `2026-01-20`), and one feed had a field (`acct_no`) that was sometimes just blank. Nothing about matching these two files was going to be a simple join.

## Building the Fix

Rather than forcing one schema to match the other, the fix was a normalization layer — a translation step that mapped both feeds into one common shape before any comparison happened. Once both sides spoke the same language (same field names, same date format, nulls handled instead of crashing), matching transactions by ID and comparing amounts was straightforward.

## The Result

Out of 150 transactions, the reconciliation correctly identified:
- 136 clean matches
- 7 real amount discrepancies, each with the exact dollar difference logged
- 7 transactions present in the internal ledger but missing entirely from the custodian statement — a real gap requiring follow-up, not just a data quality issue

## Turnaround

The build, start to finish, took under an hour — not because the problem was trivial, but because the platform's existing pattern (adapter → normalize → classify → log to audit trail) meant Client B didn't require new infrastructure, just a new mapping. That reusable pattern is the actual point of the platform: onboarding client N+1 should always be faster than client N.
