# Ledger Platform — Client Operations Runbook

This document is written for a client's own team to run and troubleshoot the platform without needing the original engineer involved. If you're reading this to operate the platform day-to-day, start here.

## What this platform does

Ledger ingests your data (claims, reconciliation feeds, etc.), validates it, applies your configured business rules, and logs every decision with a plain-language explanation. Bad or malformed data is caught and set aside before it can cause a problem, instead of failing silently.

## Prerequisites

- Docker running (for the database)
- Python 3 with `psycopg2-binary` and `redis` installed
- The platform's own Redis-in-Java cache running on port 6380

## Onboarding a new client dataset

```bash
cd onboarding
python3 onboard.py <path_to_csv> --client-name "Client Name" --type claims
```

This creates the client record, seeds a default rule set, ingests the data, and runs adjudication automatically. The summary at the end tells you how many records were processed, flagged, and how long it took.

To add data to an **existing** client instead of creating a new one:

```bash
python3 onboard.py <path_to_csv> --client-id <existing-client-uuid> --type claims
```

## Checking what got flagged, and why

Every decision the platform makes is logged with a human-readable reason. To see what's been flagged for a client:

```sql
SELECT entity_id, explanation FROM audit_log
WHERE client_id = '<client-id>'
AND explanation != 'no rule violations, claim adjudicated clean'
ORDER BY created_at DESC;
```

Every flagged record has a specific, readable reason attached — there is no "black box" decision anywhere in this system. If a record is flagged and the reason doesn't make sense, that's a signal to review the rule configuration, not to distrust the output blindly.

## Checking what was rejected at intake

Records that fail basic validation (missing fields, invalid amounts, bad dates) never reach the rules engine at all — they're quarantined with a specific reason:

```sql
SELECT raw_data, reason FROM quarantined_records
WHERE client_id = '<client-id>'
ORDER BY quarantined_at DESC;
```

## Updating business rules

Rules live in the `rule_versions` table, versioned by client. To see the current active rule set:

```sql
SELECT version_number, rule_definition FROM rule_versions
WHERE client_id = '<client-id>' AND is_active = true;
```

Rule changes should always be inserted as a **new version**, never edited in place — this preserves a full history of what the system believed at any point in time, which matters for audit and compliance.

## Getting a business summary (ROI report)

```bash
cd dashboard
python3 generate_roi_summary.py
```

This prints real numbers across all onboarded clients: how many records were auto-processed vs. flagged, dollar amounts on flagged items, and the auto-adjudication rate (how much manual review was avoided).

## Common issues

**"no active rule version found for client"** — the client was created without the default rule set being seeded. Check the client was created through `onboard.py`, not inserted directly into the `clients` table.

**Postgres connection errors** — confirm Docker is running: `docker ps | grep ledger-postgres`. If it's not listed, start it with `docker compose up -d` from `infra/docker`.

**Cache-related errors from the rules engine** — the Redis-in-Java server may not be running. Start it from `infra/redis-java` with `mvn exec:java -Dexec.mainClass="com.ledger.rediscache.App"`. The rules engine will still function correctly without it (it falls back to Postgres on every read), just without the caching speed benefit.

## What this system will not do for you

- It does not make final business decisions — every flag is a recommendation for human review, not an automatic rejection
- It does not detect fraud beyond the specific rules configured — it applies the rules it's given, consistently and transparently
- It does not replace the need for someone to periodically review whether the configured rules still match business reality
