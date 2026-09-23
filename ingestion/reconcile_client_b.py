"""
Reconciliation adapter for Client B.
Normalizes two mismatched feeds (internal ledger vs custodian
statement — different column names, different date formats,
some missing fields) into a common shape, then matches and
classifies every transaction as clean, an amount break, or
missing from one side.
"""

import csv
import sys
import psycopg2
from datetime import datetime

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

def normalize_internal(row):
    return {
        "txn_id": row["TransactionRef"],
        "amount": float(row["Amt"]),
        "date": datetime.strptime(row["TxnDate"], "%m/%d/%Y").date().isoformat(),
        "account": row["AccountNumber"] or None,
    }

def normalize_custodian(row):
    return {
        "txn_id": row["ref_id"],
        "amount": float(row["settlement_amount"]),
        "date": datetime.strptime(row["value_date"], "%Y-%m-%d").date().isoformat(),
        "account": row["acct_no"] or None,  # blank string -> None, not a crash
    }

def reconcile(internal_path, custodian_path, client_id):
    with open(internal_path, newline="") as f:
        internal = {r["txn_id"]: r for r in (normalize_internal(row) for row in csv.DictReader(f))}

    with open(custodian_path, newline="") as f:
        custodian = {r["txn_id"]: r for r in (normalize_custodian(row) for row in csv.DictReader(f))}

    all_ids = set(internal.keys()) | set(custodian.keys())

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    clean = 0
    amount_breaks = 0
    missing_from_custodian = 0
    missing_from_internal = 0

    for txn_id in sorted(all_ids):
        i = internal.get(txn_id)
        c = custodian.get(txn_id)

        if i and not c:
            explanation = f"transaction {txn_id} (${i['amount']}) present in internal ledger, missing from custodian statement"
            missing_from_custodian += 1
        elif c and not i:
            explanation = f"transaction {txn_id} (${c['amount']}) present in custodian statement, missing from internal ledger"
            missing_from_internal += 1
        elif abs(i["amount"] - c["amount"]) > 0.01:
            explanation = f"amount mismatch on {txn_id}: internal=${i['amount']}, custodian=${c['amount']}, diff=${round(i['amount']-c['amount'], 2)}"
            amount_breaks += 1
        else:
            clean += 1
            continue  # don't log clean matches to keep audit_log focused on actual breaks

        cur.execute(
            """
            INSERT INTO audit_log (client_id, event_type, entity_id, payload, explanation, created_by)
            VALUES (%s, 'decision', %s, '{}'::jsonb, %s, 'reconciliation_engine')
            """,
            (client_id, txn_id, explanation),
        )

    conn.commit()
    cur.close()
    conn.close()

    print(f"reconciliation complete: {clean} clean matches, {amount_breaks} amount breaks, "
          f"{missing_from_custodian} missing from custodian, {missing_from_internal} missing from internal")

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("usage: python reconcile_client_b.py <internal_csv> <custodian_csv> <client_id>")
        sys.exit(1)
    reconcile(sys.argv[1], sys.argv[2], sys.argv[3])
