"""
Ingestion adapter for Client A (claims adjudication).
Reads a raw claims CSV, validates every row against the data
quality gate, and either inserts it into `claims` or logs it
to `quarantined_records` with the reason it failed.
"""

import csv
import json
import sys
from datetime import datetime
import psycopg2

import os as _os

DATABASE_URL = _os.getenv("DATABASE_URL")

if DATABASE_URL:
    DB_CONFIG = {"dsn": DATABASE_URL}
else:
    DB_CONFIG = {
        "host": "localhost",
        "port": 5432,
        "dbname": "ledger",
        "user": "ledger",
        "password": "ledger_dev_pw",
    }

def validate_row(row):
    """
    Returns (is_valid, reason). reason is None if valid.
    This is the data quality gate — deliberately basic checks,
    not business rules (that's the rules engine's job later).
    """
    if not row.get("claim_id"):
        return False, "missing claim_id"

    if not row.get("procedure_code"):
        return False, "missing procedure_code"

    if not row.get("diagnosis_code"):
        return False, "missing diagnosis_code"

    try:
        amount = float(row.get("billed_amount", ""))
        if amount <= 0:
            return False, f"billed_amount must be positive, got {amount}"
    except (ValueError, TypeError):
        return False, f"billed_amount is not a valid number: {row.get('billed_amount')}"

    try:
        datetime.strptime(row.get("submitted_date", ""), "%Y-%m-%d")
    except ValueError:
        return False, f"submitted_date is not a valid YYYY-MM-DD date: {row.get('submitted_date')}"

    return True, None

def ingest(csv_path, client_id):
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    inserted = 0
    quarantined = 0

    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            is_valid, reason = validate_row(row)

            if is_valid:
                cur.execute(
                    """
                    INSERT INTO claims (
                        client_id, claim_id, desynpuf_id, provider_id,
                        provider_specialty, procedure_code, diagnosis_code,
                        claim_type, billed_amount, submitted_date
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (client_id, claim_id) DO NOTHING
                    """,
                    (
                        client_id, row["claim_id"], row["desynpuf_id"], row["provider_id"],
                        row["provider_specialty"], row["procedure_code"], row["diagnosis_code"],
                        row["claim_type"], row["billed_amount"], row["submitted_date"],
                    ),
                )
                inserted += 1
            else:
                cur.execute(
                    """
                    INSERT INTO quarantined_records (client_id, raw_data, reason)
                    VALUES (%s, %s, %s)
                    """,
                    (client_id, json.dumps(row), reason),
                )
                quarantined += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"ingestion complete: {inserted} claims inserted, {quarantined} quarantined")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python ingest_claims.py <csv_path> <client_id>")
        sys.exit(1)

    csv_path = sys.argv[1]
    client_id = sys.argv[2]
    ingest(csv_path, client_id)
