"""
AgentTrace — LLM-as-Judge Evaluator
Automatically scores each agent step output for quality.
No human labeling needed.
"""

import uuid
import httpx
import json
from datetime import datetime
from tracer.trace_db import save_eval, get_steps_for_run
import os

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# ─── EVAL CRITERIA PER STEP ───────────────────────────────────────────────────
EVAL_PROMPTS = {
    "research_company": """You are evaluating the quality of a company research summary.
Score the output from 0.0 to 1.0 based on:
- Does it mention what the company does? (0.25)
- Does it mention the market or industry? (0.25)
- Does it include any specific numbers or metrics? (0.25)
- Is it concise and well-written? (0.25)

Output ONLY valid JSON: {{"score": 0.0-1.0, "reasoning": "one sentence explanation"}}""",

    "find_recent_news": """You are evaluating the quality of a company news summary.
Score the output from 0.0 to 1.0 based on:
- Does it mention specific recent events (not generic)? (0.3)
- Does it include dates or timeframes? (0.2)
- Are the events relevant to business development? (0.3)
- Is it concise and factual? (0.2)

Output ONLY valid JSON: {{"score": 0.0-1.0, "reasoning": "one sentence explanation"}}""",

    "identify_decision_makers": """You are evaluating the quality of a decision maker identification.
Score the output from 0.0 to 1.0 based on:
- Does it identify at least 2 real people? (0.3)
- Does it include titles/roles? (0.3)
- Does it describe their focus area? (0.2)
- Are these likely actual decision makers? (0.2)

Output ONLY valid JSON: {{"score": 0.0-1.0, "reasoning": "one sentence explanation"}}""",

    "write_outreach_summary": """You are evaluating the quality of a personalized outreach email opening.
Score the output from 0.0 to 1.0 based on:
- Does it reference specific company details (not generic)? (0.3)
- Does it avoid cliche openers like "I hope this finds you well"? (0.2)
- Does it demonstrate genuine knowledge of the company? (0.3)
- Is it concise and compelling? (0.2)

Output ONLY valid JSON: {{"score": 0.0-1.0, "reasoning": "one sentence explanation"}}""",
}


def call_groq_eval(system_prompt: str, output_to_eval: str) -> dict:
    """Call Groq for evaluation. Returns {score, reasoning}."""
    if not GROQ_API_KEY:
        return {"score": 0.0, "reasoning": "GROQ_API_KEY not set"}

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Evaluate this output:\n\n{output_to_eval}"},
        ],
        "temperature": 0.0,
        "max_tokens": 200,
    }

    try:
        response = httpx.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON response
        content = content.replace("```json", "").replace("```", "").strip()
        parsed = json.loads(content)
        return {
            "score": float(parsed.get("score", 0.0)),
            "reasoning": parsed.get("reasoning", "")
        }
    except Exception as e:
        return {"score": 0.0, "reasoning": f"Eval failed: {str(e)}"}


def evaluate_run(run_id: str) -> list[dict]:
    """
    Run LLM-as-judge evals on all steps of a completed run.
    Returns list of eval results.
    """
    steps_df = get_steps_for_run(run_id)
    eval_results = []

    print(f"  Evaluating run {run_id[:8]}...")

    for _, step in steps_df.iterrows():
        step_name = step["step_name"]
        output_text = step["output_text"] or ""

        if step_name not in EVAL_PROMPTS:
            continue
        if not output_text or step["status"] != "success":
            continue

        eval_prompt = EVAL_PROMPTS[step_name]
        result = call_groq_eval(eval_prompt, output_text)

        eval_id = str(uuid.uuid4())
        evaluated_at = datetime.utcnow().isoformat()

        save_eval(
            eval_id=eval_id,
            step_id=step["step_id"],
            run_id=run_id,
            step_name=step_name,
            score=result["score"],
            reasoning=result["reasoning"],
            evaluated_at=evaluated_at
        )

        eval_results.append({
            "step_name": step_name,
            "score": result["score"],
            "reasoning": result["reasoning"],
        })

        print(f"    {step_name}: {result['score']:.2f} — {result['reasoning'][:60]}...")

    return eval_results


def evaluate_all_runs():
    """Evaluate all runs that don't have evals yet."""
    from tracer.trace_db import get_all_runs, get_connection
    import pandas as pd

    runs_df = get_all_runs()
    conn = get_connection()
    evaled_runs = pd.read_sql("SELECT DISTINCT run_id FROM evals", conn)
    conn.close()

    evaled_ids = set(evaled_runs["run_id"].tolist()) if len(evaled_runs) > 0 else set()
    pending = runs_df[~runs_df["run_id"].isin(evaled_ids)]

    print(f"\nFound {len(pending)} runs to evaluate...")
    for _, run in pending.iterrows():
        evaluate_run(run["run_id"])

    print("\nAll runs evaluated.")


if __name__ == "__main__":
    evaluate_all_runs()

    # Show summary
    from tracer.trace_db import get_connection
    import pandas as pd
    conn = get_connection()
    df = pd.read_sql("""
        SELECT e.step_name, ROUND(AVG(e.score),2) as avg_score, COUNT(*) as eval_count
        FROM evals e
        GROUP BY e.step_name
        ORDER BY avg_score DESC
    """, conn)
    conn.close()
    print("\nEval scores by step:")
    print(df.to_string())
