import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "traces.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def get_connection():
    return sqlite3.connect(DB_PATH)

def db_exists():
    return os.path.exists(DB_PATH)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            subject_id TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            total_latency_ms INTEGER,
            steps_completed INTEGER,
            status TEXT DEFAULT 'running',
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS steps (
            step_id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_name TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            latency_ms INTEGER,
            input_text TEXT,
            output_text TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            status TEXT DEFAULT 'running',
            error TEXT,
            FOREIGN KEY (run_id) REFERENCES runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS evals (
            eval_id TEXT PRIMARY KEY,
            step_id TEXT NOT NULL,
            run_id TEXT NOT NULL,
            step_name TEXT NOT NULL,
            score REAL,
            reasoning TEXT,
            evaluated_at TEXT NOT NULL,
            FOREIGN KEY (step_id) REFERENCES steps(step_id)
        );
    """)
    conn.commit()
    conn.close()

def save_run(run_id, subject_id, started_at, finished_at=None, total_latency_ms=None, steps_completed=0, status="running", error=None):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO runs
        (run_id, subject_id, started_at, finished_at, total_latency_ms, steps_completed, status, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_id, subject_id, started_at, finished_at, total_latency_ms, steps_completed, status, error))
    conn.commit()
    conn.close()

def save_step(step_id, run_id, step_name, started_at, finished_at=None, latency_ms=None,
              input_text=None, output_text=None, input_tokens=None, output_tokens=None,
              status="running", error=None):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO steps
        (step_id, run_id, step_name, started_at, finished_at, latency_ms,
         input_text, output_text, input_tokens, output_tokens, status, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (step_id, run_id, step_name, started_at, finished_at, latency_ms,
          input_text, output_text, input_tokens, output_tokens, status, error))
    conn.commit()
    conn.close()

def save_eval(eval_id, step_id, run_id, step_name, score, reasoning, evaluated_at):
    conn = get_connection()
    conn.execute("""
        INSERT OR REPLACE INTO evals
        (eval_id, step_id, run_id, step_name, score, reasoning, evaluated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (eval_id, step_id, run_id, step_name, score, reasoning, evaluated_at))
    conn.commit()
    conn.close()

def get_all_runs():
    conn = get_connection()
    df = __import__('pandas').read_sql("SELECT * FROM runs ORDER BY started_at DESC", conn)
    conn.close()
    return df

def get_steps_for_run(run_id):
    conn = get_connection()
    df = __import__('pandas').read_sql("SELECT * FROM steps WHERE run_id=? ORDER BY started_at", conn, params=(run_id,))
    conn.close()
    return df

def get_evals_for_run(run_id):
    conn = get_connection()
    df = __import__('pandas').read_sql("SELECT * FROM evals WHERE run_id=? ORDER BY evaluated_at", conn, params=(run_id,))
    conn.close()
    return df

def get_recent_eval_scores(step_name, limit=20):
    conn = get_connection()
    df = __import__('pandas').read_sql(
        "SELECT score, evaluated_at FROM evals WHERE step_name=? ORDER BY evaluated_at DESC LIMIT ?",
        conn, params=(step_name, limit)
    )
    conn.close()
    return df

init_db()
