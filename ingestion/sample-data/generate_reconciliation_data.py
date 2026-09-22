"""
Client B curveball data — two feeds that should reconcile:
an internal ledger and a "custodian statement" export.
Deliberately messy: different column names, inconsistent
date formats, a missing field on some rows, and a mix of
genuine breaks vs. just formatting noise.
"""

import csv
import random
from datetime import date, timedelta

random.seed(7)

def random_date_slash():
    d = date(2026, 1, 1) + timedelta(days=random.randint(0, 120))
    return d.strftime("%m/%d/%Y")  # internal ledger uses US slash format

def random_date_dash():
    d = date(2026, 1, 1) + timedelta(days=random.randint(0, 120))
    return d.strftime("%Y-%m-%d")  # custodian uses ISO format

def generate():
    internal_rows = []
    custodian_rows = []

    for i in range(1, 151):
        txn_id = f"TXN{i:05d}"
        amount = round(random.uniform(500, 50000), 2)
        d = date(2026, 1, 1) + timedelta(days=random.randint(0, 120))

        # internal ledger row — its own column naming convention
        internal_rows.append({
            "TransactionRef": txn_id,
            "Amt": amount,
            "TxnDate": d.strftime("%m/%d/%Y"),
            "AccountNumber": f"ACC{random.randint(1000,9999)}",
        })

        # custodian statement — different column names, different date format
        custodian_amount = amount
        custodian_date = d.strftime("%Y-%m-%d")

        # inject real breaks in ~8% of rows
        roll = random.random()
        if roll < 0.05:
            custodian_amount = round(amount + random.choice([-100, 250, 500]), 2)  # genuine amount mismatch
        elif roll < 0.08:
            continue  # missing entirely from custodian feed — a real reconciliation break

        row = {
            "ref_id": txn_id,
            "settlement_amount": custodian_amount,
            "value_date": custodian_date,
        }
        # ~10% of custodian rows are missing the account field entirely — realistic messiness
        if random.random() > 0.10:
            row["acct_no"] = f"ACC{random.randint(1000,9999)}"

        custodian_rows.append(row)

    with open("client_b_internal_ledger.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["TransactionRef", "Amt", "TxnDate", "AccountNumber"])
        writer.writeheader()
        writer.writerows(internal_rows)

    with open("client_b_custodian_statement.csv", "w", newline="") as f:
        # not every row has the same keys (missing acct_no sometimes) — DictWriter needs the full fieldname set
        writer = csv.DictWriter(f, fieldnames=["ref_id", "settlement_amount", "value_date", "acct_no"])
        writer.writeheader()
        writer.writerows(custodian_rows)

    print(f"generated {len(internal_rows)} internal ledger rows -> client_b_internal_ledger.csv")
    print(f"generated {len(custodian_rows)} custodian statement rows -> client_b_custodian_statement.csv")
    print(f"({len(internal_rows) - len(custodian_rows)} rows missing from custodian feed)")

if __name__ == "__main__":
    generate()
