"""
AgentTrace — Core Tracer
Wraps the lead agent and traces every step automatically.
"""

import time
import uuid
from datetime import datetime
from typing import Callable
from tracer.trace_db import save_run, save_step

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(str(text)) // 4

class StepTracer:
    """Context manager that traces a single agent step."""

    def __init__(self, run_id: str, step_name: str, input_text: str = ""):
        self.run_id = run_id
        self.step_name = step_name
        self.step_id = str(uuid.uuid4())
        self.input_text = input_text
        self.started_at = datetime.utcnow().isoformat()
        self.start_time = time.time()
        self.output_text = ""
        self.error = None

    def __enter__(self):
        save_step(
            step_id=self.step_id,
            run_id=self.run_id,
            step_name=self.step_name,
            started_at=self.started_at,
            input_text=self.input_text[:2000],
            input_tokens=estimate_tokens(self.input_text),
            status="running"
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        finished_at = datetime.utcnow().isoformat()
        latency_ms = int((time.time() - self.start_time) * 1000)
        status = "error" if exc_type else "success"
        error = str(exc_val) if exc_val else None

        save_step(
            step_id=self.step_id,
            run_id=self.run_id,
            step_name=self.step_name,
            started_at=self.started_at,
            finished_at=finished_at,
            latency_ms=latency_ms,
            input_text=self.input_text[:2000],
            output_text=self.output_text[:2000],
            input_tokens=estimate_tokens(self.input_text),
            output_tokens=estimate_tokens(self.output_text),
            status=status,
            error=error
        )
        return False  # Don't suppress exceptions


class RunTracer:
    """Traces a complete agent run across all steps."""

    def __init__(self, subject_id: str):
        self.run_id = str(uuid.uuid4())
        self.subject_id = subject_id
        self.started_at = datetime.utcnow().isoformat()
        self.start_time = time.time()

    def __enter__(self):
        save_run(
            run_id=self.run_id,
            subject_id=self.subject_id,
            started_at=self.started_at,
            status="running"
        )
        print(f"  Tracing run {self.run_id[:8]}...")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        finished_at = datetime.utcnow().isoformat()
        total_latency_ms = int((time.time() - self.start_time) * 1000)
        status = "error" if exc_type else "success"
        error = str(exc_val) if exc_val else None

        save_run(
            run_id=self.run_id,
            subject_id=self.subject_id,
            started_at=self.started_at,
            finished_at=finished_at,
            total_latency_ms=total_latency_ms,
            status=status,
            error=error
        )
        return False
