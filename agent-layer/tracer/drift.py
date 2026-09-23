"""
AgentTrace — Drift Detector
Monitors eval scores over time and alerts when quality degrades.
"""

import pandas as pd
from datetime import datetime
from tracer.trace_db import get_connection

ALERT_THRESHOLD = 0.70
DRIFT_THRESHOLD = 0.15

STEP_NAMES = [
    "review_claim",
]


def get_score_history() -> pd.DataFrame:
    """Get all eval scores with run metadata."""
    conn = get_connection()
    df = pd.read_sql("""
        SELECT
            e.step_name,
            e.score,
            e.reasoning,
            e.evaluated_at,
            r.subject_id,
            r.total_latency_ms,
            r.started_at
        FROM evals e
        JOIN runs r ON e.run_id = r.run_id
        ORDER BY e.evaluated_at ASC
    """, conn)
    conn.close()
    return df


def get_step_stats() -> pd.DataFrame:
    """Get current stats per step."""
    conn = get_connection()
    df = pd.read_sql("""
        SELECT
            step_name,
            ROUND(AVG(score), 3) as avg_score,
            ROUND(MIN(score), 3) as min_score,
            ROUND(MAX(score), 3) as max_score,
            COUNT(*) as eval_count
        FROM evals
        GROUP BY step_name
        ORDER BY avg_score ASC
    """, conn)
    conn.close()
    return df


def get_latency_stats() -> pd.DataFrame:
    """Get latency stats per step."""
    conn = get_connection()
    df = pd.read_sql("""
        SELECT
            step_name,
            ROUND(AVG(latency_ms)) as avg_latency_ms,
            ROUND(MAX(latency_ms)) as max_latency_ms,
            COUNT(*) as run_count
        FROM steps
        WHERE status = 'success'
        GROUP BY step_name
        ORDER BY avg_latency_ms DESC
    """, conn)
    conn.close()
    return df


def check_alerts() -> list[dict]:
    """
    Check for quality issues and return list of alerts.
    Two types:
    1. Low score alert — step avg below ALERT_THRESHOLD
    2. Drift alert — recent scores significantly lower than historical
    """
    alerts = []
    history = get_score_history()

    if history.empty:
        return alerts

    for step_name in STEP_NAMES:
        step_data = history[history["step_name"] == step_name]
        if len(step_data) < 2:
            continue

        avg_score = step_data["score"].mean()
        latest_score = step_data["score"].iloc[-1]
        latest_subject_id = step_data["subject_id"].iloc[-1]

        # Alert 1: Low average score
        if avg_score < ALERT_THRESHOLD:
            alerts.append({
                "type": "LOW_QUALITY",
                "severity": "HIGH" if avg_score < 0.5 else "MEDIUM",
                "step": step_name,
                "avg_score": round(avg_score, 2),
                "message": f"Step '{step_name}' avg score {avg_score:.2f} is below threshold {ALERT_THRESHOLD}",
                "detected_at": datetime.utcnow().isoformat(),
            })

        # Alert 2: Drift — latest score much lower than average
        if len(step_data) >= 2:
            historical_avg = step_data["score"].iloc[:-1].mean()
            drift = historical_avg - latest_score
            if drift > DRIFT_THRESHOLD:
                alerts.append({
                    "type": "DRIFT",
                    "severity": "HIGH" if drift > 0.3 else "MEDIUM",
                    "step": step_name,
                    "historical_avg": round(historical_avg, 2),
                    "latest_score": round(latest_score, 2),
                    "drift": round(drift, 2),
                    "subject_id": latest_subject_id,
                    "message": f"Step '{step_name}' dropped {drift:.2f} points on '{latest_subject_id}' run (was {historical_avg:.2f}, now {latest_score:.2f})",
                    "detected_at": datetime.utcnow().isoformat(),
                })

    return alerts


def get_health_summary() -> dict:
    """Overall agent health summary."""
    stats = get_step_stats()
    latency = get_latency_stats()
    alerts = check_alerts()

    if stats.empty:
        return {"status": "no_data", "alerts": []}

    overall_score = stats["avg_score"].mean()

    if overall_score >= 0.85:
        status = "healthy"
    elif overall_score >= 0.70:
        status = "degraded"
    else:
        status = "critical"

    return {
        "status": status,
        "overall_score": round(float(overall_score), 3),
        "step_stats": stats.to_dict(orient="records"),
        "latency_stats": latency.to_dict(orient="records"),
        "alerts": alerts,
        "alert_count": len(alerts),
        "checked_at": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    print("\nAgentTrace — Health Report")
    print("="*50)

    summary = get_health_summary()
    print(f"Overall Status: {summary['status'].upper()}")
    print(f"Overall Score:  {summary['overall_score']}")
    print(f"Alerts:         {summary['alert_count']}")

    print("\nStep Scores:")
    for step in summary["step_stats"]:
        bar = "█" * int(step["avg_score"] * 10)
        print(f"  {step['step_name']:<30} {bar:<10} {step['avg_score']:.2f}")

    print("\nStep Latency:")
    for step in summary["latency_stats"]:
        print(f"  {step['step_name']:<30} {step['avg_latency_ms']:.0f}ms avg")

    if summary["alerts"]:
        print("\nActive Alerts:")
        for alert in summary["alerts"]:
            print(f"  [{alert['severity']}] {alert['type']}: {alert['message']}")
    else:
        print("\nNo alerts")
