"""
ROI summary — pulls real numbers out of audit_log and claims/
quarantined_records to answer the question every client actually
cares about: what did this platform catch, and what's it worth.
"""

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "ledger",
    "user": "ledger",
    "password": "ledger_dev_pw",
}

def generate_report():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, name, client_type FROM clients ORDER BY name")
    clients = cur.fetchall()

    print("=" * 70)
    print("LEDGER PLATFORM — ROI SUMMARY")
    print("=" * 70)

    total_flagged = 0
    total_clean = 0
    total_quarantined = 0
    total_overbilled_amount = 0
    total_recon_breaks = 0

    for client in clients:
        cid = client["id"]
        print(f"\n--- {client['name']} ({client['client_type']}) ---")

        cur.execute(
            "SELECT COUNT(*) as n FROM claims WHERE client_id = %s AND status = 'flagged'", (cid,)
        )
        flagged = cur.fetchone()["n"]

        cur.execute(
            "SELECT COUNT(*) as n FROM claims WHERE client_id = %s AND status = 'adjudicated'", (cid,)
        )
        clean = cur.fetchone()["n"]

        cur.execute(
            "SELECT COUNT(*) as n FROM quarantined_records WHERE client_id = %s", (cid,)
        )
        quarantined = cur.fetchone()["n"]

        cur.execute(
            """
            SELECT COALESCE(SUM(c.billed_amount), 0) as total
            FROM claims c
            JOIN audit_log a ON a.entity_id = c.claim_id AND a.client_id = c.client_id
            WHERE c.client_id = %s AND a.explanation LIKE '%%overbilling%%'
            """,
            (cid,),
        )
        overbilled = cur.fetchone()["total"] or 0

        cur.execute(
            "SELECT COUNT(*) as n FROM audit_log WHERE client_id = %s AND created_by = 'reconciliation_engine'",
            (cid,),
        )
        recon_breaks = cur.fetchone()["n"]

        if flagged or clean:
            print(f"  Claims processed: {flagged + clean}")
            print(f"  Flagged for review: {flagged}")
            print(f"  Clean, auto-adjudicated: {clean}")
            if overbilled:
                print(f"  Dollar amount on flagged overbilling claims: ${overbilled:,.2f}")
        if quarantined:
            print(f"  Records quarantined at intake (bad data caught before processing): {quarantined}")
        if recon_breaks:
            print(f"  Reconciliation breaks identified: {recon_breaks}")

        total_flagged += flagged
        total_clean += clean
        total_quarantined += quarantined
        total_overbilled_amount += overbilled
        total_recon_breaks += recon_breaks

    print("\n" + "=" * 70)
    print("PLATFORM TOTALS")
    print("=" * 70)
    print(f"Total claims auto-adjudicated (no manual review needed): {total_clean}")
    print(f"Total claims flagged for review: {total_flagged}")
    print(f"Total bad records caught at intake: {total_quarantined}")
    print(f"Total dollar value on flagged overbilling: ${total_overbilled_amount:,.2f}")
    print(f"Total reconciliation breaks identified: {total_recon_breaks}")

    if total_flagged + total_clean > 0:
        auto_rate = round(100 * total_clean / (total_flagged + total_clean), 1)
        print(f"Auto-adjudication rate (no analyst needed): {auto_rate}%")

    cur.close()
    conn.close()

if __name__ == "__main__":
    generate_report()
