"""
Onboarding CLI — the reusable entry point for standing up a new
client on the platform. Wraps the ingestion and rules-engine
adapters already proven on Client A and Client B, so onboarding
client N+1 is one command instead of a bespoke script.
"""

import argparse
import subprocess
import sys
import time
import psycopg2

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "ledger",
    "user": "ledger",
    "password": "ledger_dev_pw",
}

def get_or_create_client(name, client_type, existing_id=None):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    if existing_id:
        cur.execute("SELECT id, name FROM clients WHERE id = %s", (existing_id,))
        row = cur.fetchone()
        if not row:
            print(f"ERROR: no client found with id {existing_id}")
            sys.exit(1)
        cur.close()
        conn.close()
        return row[0]

    cur.execute(
        "INSERT INTO clients (name, client_type) VALUES (%s, %s) RETURNING id",
        (name, client_type),
    )
    new_id = cur.fetchone()[0]

    if client_type == "claims":
        default_rules = {
            "overbilling_multiplier": 3.0,
            "expected_amounts": {
                "99213": 110, "99214": 165, "71020": 85, "80053": 45,
                "93000": 60, "36415": 15, "97110": 55, "99396": 195,
            },
            "implausible_pairings": [
                {"procedure_code": "93000", "diagnosis_code": "3659",
                 "reason": "EKG has no clinical link to glaucoma diagnosis"},
            ],
        }
        import json
        cur.execute(
            "INSERT INTO rule_versions (client_id, version_number, rule_definition, created_by) VALUES (%s, 1, %s, %s)",
            (new_id, json.dumps(default_rules), "onboarding_cli"),
        )
        print(f"seeded default rule set (v1) for new client")

    conn.commit()
    cur.close()
    conn.close()
    print(f"created new client: {name} ({new_id})")
    return new_id

def onboard_claims(csv_path, client_id):
    print("\n--- running claims ingestion adapter ---")
    result = subprocess.run(
        ["python3", "../ingestion/ingest_claims.py", csv_path, str(client_id)],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        return False

    print("--- running rules engine ---")
    result = subprocess.run(
        ["python3", "../rules-engine/run_rules_engine.py", str(client_id)],
        capture_output=True, text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        return False
    return True

def onboard_reconciliation(csv_path, client_id):
    print("\nreconciliation onboarding requires two files (internal + custodian).")
    print("use: python3 ../ingestion/reconcile_client_b.py <internal_csv> <custodian_csv> <client_id>")
    print("this CLI currently automates single-file onboarding (claims-type clients).")
    return None

def main():
    parser = argparse.ArgumentParser(description="Onboard a new client onto the Ledger platform")
    parser.add_argument("csv_path", help="Path to the client's raw data file")
    parser.add_argument("--client-name", help="Name for a new client (required if not using --client-id)")
    parser.add_argument("--client-id", help="Existing client UUID to onboard data into")
    parser.add_argument("--type", choices=["claims", "reconciliation"], required=True,
                         help="What kind of data this is")
    args = parser.parse_args()

    if not args.client_id and not args.client_name:
        print("ERROR: must provide either --client-name (new client) or --client-id (existing client)")
        sys.exit(1)

    start_time = time.time()
    print(f"=== onboarding started: {args.client_name or args.client_id} ({args.type}) ===")

    client_id = get_or_create_client(args.client_name, args.type, existing_id=args.client_id)

    if args.type == "claims":
        success = onboard_claims(args.csv_path, client_id)
    else:
        success = onboard_reconciliation(args.csv_path, client_id)

    elapsed = round(time.time() - start_time, 2)

    print(f"\n=== onboarding {'complete' if success else 'incomplete'} in {elapsed}s ===")
    print(f"client_id: {client_id}")

if __name__ == "__main__":
    main()
