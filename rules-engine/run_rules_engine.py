"""
Rules engine for Client A (claims adjudication).
Reads pending claims, applies configurable rules loaded from
rule_versions, writes every decision to audit_log with a
human-readable explanation, and updates claim status.
"""

import sys
import psycopg2
import psycopg2.extras
import json
import redis
from collections import defaultdict

# Our own Redis-in-Java, not real Redis - same protocol, our implementation
cache = redis.Redis(host="localhost", port=6380, decode_responses=True)

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "ledger",
    "user": "ledger",
    "password": "ledger_dev_pw",
}

def load_active_rules(cur, client_id):
    cache_key = f"rules:{client_id}"

    cached = cache.hgetall(cache_key)
    if cached and "id" in cached:
        print(f"cache HIT for {cache_key}")
        return cached["id"], json.loads(cached["rule_definition"])

    print(f"cache MISS for {cache_key}, loading from Postgres")
    cur.execute(
        "SELECT id, rule_definition FROM rule_versions WHERE client_id = %s AND is_active = true ORDER BY version_number DESC LIMIT 1",
        (client_id,),
    )
    row = cur.fetchone()
    if not row:
        raise Exception(f"no active rule version found for client {client_id}")

    rule_version_id = str(row["id"])
    rule_definition = row["rule_definition"]

    cache.hset(cache_key, mapping={
        "id": rule_version_id,
        "rule_definition": json.dumps(rule_definition),
    })

    return rule_version_id, rule_definition

def check_overbilling(claim, rules):
    expected = rules["expected_amounts"].get(claim["procedure_code"])
    if expected is None:
        return None
    threshold = expected * rules["overbilling_multiplier"]
    if float(claim["billed_amount"]) > threshold:
        return f"billed ${claim['billed_amount']} exceeds {rules['overbilling_multiplier']}x expected (${expected}) for procedure {claim['procedure_code']}"
    return None

def check_implausible_pairing(claim, rules):
    for pairing in rules["implausible_pairings"]:
        if claim["procedure_code"] == pairing["procedure_code"] and claim["diagnosis_code"] == pairing["diagnosis_code"]:
            return pairing["reason"]
    return None

def check_duplicates(claims):
    """
    Group claims by (patient, procedure, date) — anything with
    more than one claim in a group is a duplicate billing flag.
    Returns a set of claim ids that are duplicates.
    """
    groups = defaultdict(list)
    for c in claims:
        key = (c["desynpuf_id"], c["procedure_code"], str(c["submitted_date"]))
        groups[key].append(c["id"])

    duplicate_ids = set()
    for key, ids in groups.items():
        if len(ids) > 1:
            duplicate_ids.update(ids)
    return duplicate_ids

def run(client_id):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    rule_version_id, rules = load_active_rules(cur, client_id)
    print(f"using rule version {rule_version_id}")

    cur.execute("SELECT * FROM claims WHERE client_id = %s AND status = 'pending'", (client_id,))
    claims = cur.fetchall()
    print(f"found {len(claims)} pending claims")

    duplicate_ids = check_duplicates(claims)

    flagged = 0
    clean = 0

    for claim in claims:
        reasons = []

        overbilling_reason = check_overbilling(claim, rules)
        if overbilling_reason:
            reasons.append(("overbilling", overbilling_reason))

        pairing_reason = check_implausible_pairing(claim, rules)
        if pairing_reason:
            reasons.append(("implausible_pairing", pairing_reason))

        if claim["id"] in duplicate_ids:
            reasons.append(("duplicate_billing", f"duplicate claim for patient {claim['desynpuf_id']}, procedure {claim['procedure_code']}, date {claim['submitted_date']}"))

        if reasons:
            explanation = "; ".join(f"[{rule}] {reason}" for rule, reason in reasons)
            cur.execute(
                """
                INSERT INTO audit_log (client_id, event_type, entity_id, rule_version_id, payload, explanation, created_by)
                VALUES (%s, 'decision', %s, %s, %s, %s, 'rules_engine')
                """,
                (client_id, claim["claim_id"], rule_version_id, json.dumps({"reasons": [r for r, _ in reasons]}), explanation, ),
            )
            cur.execute("UPDATE claims SET status = 'flagged' WHERE id = %s", (claim["id"],))
            flagged += 1
        else:
            cur.execute(
                """
                INSERT INTO audit_log (client_id, event_type, entity_id, rule_version_id, payload, explanation, created_by)
                VALUES (%s, 'decision', %s, %s, %s, 'no rule violations, claim adjudicated clean', 'rules_engine')
                """,
                (client_id, claim["claim_id"], rule_version_id, json.dumps({"reasons": []})),
            )
            cur.execute("UPDATE claims SET status = 'adjudicated' WHERE id = %s", (claim["id"],))
            clean += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"rules engine complete: {flagged} flagged, {clean} clean")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python run_rules_engine.py <client_id>")
        sys.exit(1)
    run(sys.argv[1])
