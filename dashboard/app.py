"""
Ledger Platform dashboard — visual view over the same real data
generate_roi_summary.py reports, plus per-client drill-down into
flagged records and quarantined records.
"""

import streamlit as st
import psycopg2
import psycopg2.extras
import pandas as pd

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "ledger",
    "user": "ledger",
    "password": "ledger_dev_pw",
}

def get_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=psycopg2.extras.RealDictCursor)

st.set_page_config(page_title="Ledger Platform", layout="wide")
st.title("Ledger Platform")
st.caption("Client data operations, adjudication, and reconciliation")

conn = get_conn()
cur = conn.cursor()

cur.execute("SELECT id, name, client_type FROM clients ORDER BY name")
clients = cur.fetchall()

# Platform-wide totals
cur.execute("SELECT COUNT(*) as n FROM claims WHERE status = 'adjudicated'")
total_clean = cur.fetchone()["n"]
cur.execute("SELECT COUNT(*) as n FROM claims WHERE status = 'flagged'")
total_flagged = cur.fetchone()["n"]
cur.execute("SELECT COUNT(*) as n FROM quarantined_records")
total_quarantined = cur.fetchone()["n"]
cur.execute("SELECT COUNT(*) as n FROM audit_log WHERE created_by = 'reconciliation_engine'")
total_recon = cur.fetchone()["n"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Auto-adjudicated", total_clean)
col2.metric("Flagged for review", total_flagged)
col3.metric("Quarantined at intake", total_quarantined)
col4.metric("Reconciliation breaks", total_recon)

if total_clean + total_flagged > 0:
    rate = round(100 * total_clean / (total_clean + total_flagged), 1)
    st.metric("Auto-adjudication rate", f"{rate}%")

st.divider()

client_names = {c["id"]: c["name"] for c in clients}
selected = st.selectbox("Select a client", options=[c["id"] for c in clients],
                         format_func=lambda cid: client_names[cid])

st.subheader(f"Flagged records — {client_names[selected]}")
cur.execute(
    "SELECT entity_id, explanation, created_at FROM audit_log "
    "WHERE client_id = %s AND explanation != 'no rule violations, claim adjudicated clean' "
    "ORDER BY created_at DESC",
    (selected,),
)
flagged_rows = cur.fetchall()
if flagged_rows:
    st.dataframe(pd.DataFrame(flagged_rows), use_container_width=True)
else:
    st.info("No flagged records for this client.")

st.subheader(f"Quarantined records — {client_names[selected]}")
cur.execute(
    "SELECT raw_data, reason, quarantined_at FROM quarantined_records WHERE client_id = %s ORDER BY quarantined_at DESC",
    (selected,),
)
quarantined_rows = cur.fetchall()
if quarantined_rows:
    st.dataframe(pd.DataFrame(quarantined_rows), use_container_width=True)
else:
    st.info("No quarantined records for this client.")

cur.close()
conn.close()
