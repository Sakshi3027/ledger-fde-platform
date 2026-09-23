# Ledger — Financial Data Operations Deployment Platform

> A platform that stands up automated claims, reconciliation, and compliance workflows for financial services clients, with a custom-built Redis clone as its infrastructure layer.

## What this is

Ledger simulates the core of forward-deployed engineering work: taking a client's raw, often messy data, standing up a working automated pipeline fast, and proving it stays trustworthy over time. It handles two distinct client workflows on one shared platform pattern, and includes an infrastructure component (a Redis server clone, built from scratch in Java) that the platform actually depends on in production, not as a side demo.

## What's actually built and verified

**Three onboarded clients, all with real data flowing through them:**
- **Client A — Claims Adjudication.** CMS DE-SynPUF-grounded synthetic claims data. Ingestion with a proven data quality gate (verified catching 5 distinct failure modes). Rules engine applying overbilling, duplicate billing, and implausible diagnosis/procedure pairing checks, with every decision logged and explained in plain language.
- **Client B — Reconciliation.** Two intentionally mismatched data feeds (different column names, different date formats, missing fields) reconciled into clean matches, amount breaks, and missing-transaction breaks. See [`docs/case-studies/client-b-onboarding.md`](docs/case-studies/client-b-onboarding.md) for the real onboarding writeup.
- **Client C — Claims.** Onboarded through the CLI in 1.0 second, proving the onboarding pattern generalizes rather than being a one-off.

**Platform-wide results** (live, real numbers — regenerate anytime with `dashboard/generate_roi_summary.py`):
- 248 records auto-adjudicated, 95.8% auto-adjudication rate
- 11 records flagged for human review, each with a specific, readable reason
- 5 malformed records caught and quarantined before ever reaching business logic
- 14 reconciliation breaks identified with exact dollar differences

## Architecture
```
Client data source (CSV)
|
v
Ingestion Adapter (per client type)
|
v
Data Quality Gate (validates, quarantines bad records with a reason)
|
v
Rules Engine (versioned, configurable per client) <---> Redis-in-Java cache
| (rule lookups, graceful
v fallback to Postgres
Audit Trail (append-only, every decision explained) if unavailable)
|
v
Dashboard (Streamlit) + ROI summary
```

**Infra:**
- **Redis-in-Java** — custom RESP-protocol server built from scratch: 9 commands across string and hash types, AOF persistence (verified surviving a full restart), thread-per-connection concurrency (verified with simultaneous clients), LRU eviction, benchmarked against real Redis. See [`infra/redis-java/README.md`](infra/redis-java/README.md).
- **PostgreSQL** — durable storage for clients, versioned rules, claims, audit log, quarantined records
- **Docker Compose** — isolated local infra

## Agent layer: judgment for the cases rules can't cleanly resolve

Not every claim is a clean pass or fail. Claims between 1.5x and 3x their expected amount fall in a gray zone the deterministic rules engine can't confidently resolve on its own. Instead of silently auto-clearing them, these get routed to an LLM agent for judgment.

Built by adapting the tracer, LLM-as-judge evaluator, and drift detector from [AgentTrace](https://github.com/Sakshi3027/agenttrace), a separate observability project, into Ledger's own agent layer:

- Every agent call is traced (input, output, latency) and scored for quality automatically, no human labeling needed
- Every decision is logged to the same `audit_log` as every other decision, with the agent's specific reasoning attached
- Drift detection watches for quality degradation over time, verified with a real test: a deliberately bad agent output was fed through the same pipeline, and both the low-quality alert and the drift alert fired correctly, citing the exact claim, the exact score drop, and the exact historical average it dropped from

See [`agent-layer/`](agent-layer/) for the review agent and adapted tracer module.

## Onboarding a new client

```bash
cd onboarding
python3 onboard.py <path_to_csv> --client-name "Client Name" --type claims
```

Creates the client, seeds a default rule set, ingests the data, runs adjudication, and reports elapsed time. One command instead of a bespoke script per client.

## Running the dashboard

```bash
cd dashboard
streamlit run app.py
```

## Operating this platform without the original engineer

See [`docs/runbooks/client-operations-runbook.md`](docs/runbooks/client-operations-runbook.md) — written for a client's own team to run and troubleshoot the system independently.

## Resilience

The rules engine's cache layer degrades gracefully: if Redis-in-Java is unavailable, it falls back to Postgres automatically with a visible warning, rather than failing. This was proven with an actual chaos test (killing the cache server mid-run), not assumed from the code.

## Tech stack

Python, PostgreSQL, Java (custom Redis implementation), Streamlit, Docker

## Author

Sakshi Chavan — [GitHub](https://github.com/Sakshi3027) | [LinkedIn](https://linkedin.com/in/sakshi-v-chavan)
