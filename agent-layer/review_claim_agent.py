"""
Claim review agent — handles claims that fall in a gray zone the
deterministic rules engine can't cleanly resolve (elevated but not
over the hard overbilling threshold). Uses an LLM to make a judgment
call, wrapped end-to-end in AgentTrace's tracer so every decision is
traced, scored, and watched for drift over time.
"""

import os
import sys
import httpx
import json

sys.path.insert(0, os.path.dirname(__file__))
import uuid
from datetime import datetime, timezone
from tracer.tracer import RunTracer, StepTracer
from tracer.evaluator import call_groq_eval, EVAL_PROMPTS
from tracer.trace_db import save_eval

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

REVIEW_PROMPT = """You are a claims review analyst. You will be given a claim's
details. Decide whether to APPROVE, DENY, or ESCALATE it for human review, and
give a brief, specific reason referencing the actual claim details.

Respond with ONLY valid JSON in this exact shape:
{{"decision": "APPROVE|DENY|ESCALATE", "reasoning": "one to two sentences, specific to this claim"}}

Claim details:
- Procedure code: {procedure_code}
- Diagnosis code: {diagnosis_code}
- Billed amount: ${billed_amount}
- Expected amount for this procedure: ${expected_amount}
- Ratio of billed to expected: {ratio}x
"""

def call_review_agent(claim, expected_amount):
    """Makes the actual judgment call via Groq. Returns decision dict."""
    if not GROQ_API_KEY:
        return {"decision": "ESCALATE", "reasoning": "GROQ_API_KEY not set, defaulting to human review"}

    ratio = round(float(claim["billed_amount"]) / expected_amount, 2)
    prompt = REVIEW_PROMPT.format(
        procedure_code=claim["procedure_code"],
        diagnosis_code=claim["diagnosis_code"],
        billed_amount=claim["billed_amount"],
        expected_amount=expected_amount,
        ratio=ratio,
    )

    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": 400,
    }

    try:
        response = httpx.post(GROQ_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        content = content.replace("```json", "").replace("```", "").strip()
        return json.loads(content)
    except Exception as e:
        return {"decision": "ESCALATE", "reasoning": f"agent call failed: {str(e)}, defaulting to human review"}


def review_claim(claim, expected_amount):
    """
    Traced entry point: wraps the agent call in RunTracer/StepTracer,
    evaluates the output quality, and returns the decision plus the
    trace/eval metadata for logging to Ledger's own audit_log.
    """
    with RunTracer(subject_id=claim["claim_id"]) as run:
        with StepTracer(run.run_id, "review_claim", input_text=json.dumps(claim, default=str)) as step:
            result = call_review_agent(claim, expected_amount)
            step.output_text = json.dumps(result)

        eval_prompt = EVAL_PROMPTS["review_claim"]
        eval_result = call_groq_eval(eval_prompt, json.dumps(result))

        save_eval(
            eval_id=str(uuid.uuid4()),
            step_id=step.step_id,
            run_id=run.run_id,
            step_name="review_claim",
            score=eval_result["score"],
            reasoning=eval_result["reasoning"],
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

    return {
        "decision": result.get("decision", "ESCALATE"),
        "reasoning": result.get("reasoning", "no reasoning provided"),
        "run_id": run.run_id,
        "eval_score": eval_result["score"],
        "eval_reasoning": eval_result["reasoning"],
    }


if __name__ == "__main__":
    # quick manual test
    test_claim = {
        "claim_id": "CLM_TEST_001",
        "procedure_code": "99213",
        "diagnosis_code": "4019",
        "billed_amount": 220.00,
    }
    result = review_claim(test_claim, expected_amount=110)
    print(json.dumps(result, indent=2))
