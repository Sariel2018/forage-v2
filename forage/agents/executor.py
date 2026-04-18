"""Executor: runs the action script produced by the Planner.

Unlike Evaluator and Planner, the Executor is NOT an LLM agent.
It simply runs action.py and monitors execution (timeout, request budget, errors).
This keeps execution deterministic and auditable.

Workspace layout (v2):
    plan_ws/        # Planner's private workspace (action.py lives here)
      action.py
      shared/       # symlink -> ../shared
    eval_ws/        # Evaluator's private workspace (eval.py lives here)
      eval.py
      shared/       # symlink -> ../shared
    shared/         # shared workspace
      dataset/      # records written by action.py
      metrics.json  # output of eval.py

Scripts access the shared workspace via the ./shared/ symlink in their cwd.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionResult:
    records_collected: int
    requests_used: int
    duration_seconds: float
    stdout: str
    stderr: str
    exit_code: int
    error: str | None = None


def _count_records(dataset_dir: Path) -> int:
    """Count JSONL lines (falling back to JSON files) under dataset_dir."""
    records = 0
    if not dataset_dir.is_dir():
        return 0
    for f in dataset_dir.rglob("*.jsonl"):
        try:
            with open(f) as fh:
                records += sum(1 for _ in fh)
        except (OSError, UnicodeDecodeError):
            pass
    if records == 0:
        for _ in dataset_dir.rglob("*.json"):
            records += 1
    return records


def execute_collection(
    plan_ws: Path,
    shared_ws: Path,
    script_path: str = "action.py",
    timeout: int = 1800,  # 30 min default
    round_id: int = 0,
) -> ExecutionResult:
    """Run Planner's action.py with cwd=plan_ws.

    Records are written to shared_ws/dataset/ (accessed via ./shared/dataset/
    symlink from plan_ws). Records are counted from shared_ws/dataset/ after
    the script completes.

    The script is expected to:
    - Save JSONL files to ./shared/dataset/ (i.e. shared_ws/dataset/)
    - Print a summary line: FORAGE_RESULT:{"records": N, "requests": M}
    """
    full_path = plan_ws / script_path
    if not full_path.is_file():
        return ExecutionResult(
            records_collected=0,
            requests_used=0,
            duration_seconds=0,
            stdout="",
            stderr=f"Script not found: {script_path}",
            exit_code=1,
            error="script_not_found",
        )

    dataset_dir = shared_ws / "dataset"

    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(full_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(plan_ws),
        )
        duration = time.time() - t0

        # Parse result summary from stdout
        records = 0
        requests = 0
        for line in result.stdout.splitlines():
            if line.startswith("FORAGE_RESULT:"):
                try:
                    data = json.loads(line[len("FORAGE_RESULT:"):])
                    records = data.get("records", 0)
                    requests = data.get("requests", 0)
                except json.JSONDecodeError:
                    pass

        # If no FORAGE_RESULT line, count files in shared_ws/dataset/
        if records == 0:
            records = _count_records(dataset_dir)

        # Archive full stdout/stderr to disk per round
        log_dir = plan_ws / "cli_logs"
        log_dir.mkdir(exist_ok=True)
        prefix = f"r{round_id:02d}" if round_id > 0 else "r00"
        if result.stdout:
            (log_dir / f"{prefix}_executor_stdout.txt").write_text(result.stdout)
        if result.stderr:
            (log_dir / f"{prefix}_executor_stderr.txt").write_text(result.stderr)

        return ExecutionResult(
            records_collected=records,
            requests_used=requests,
            duration_seconds=duration,
            stdout=result.stdout[-5000:],  # truncated for agent context
            stderr=result.stderr[-2000:],
            exit_code=result.returncode,
        )

    except subprocess.TimeoutExpired:
        duration = time.time() - t0
        # Count records already written to shared_ws/dataset/ before timeout
        records = _count_records(dataset_dir)
        return ExecutionResult(
            records_collected=records,
            requests_used=0,
            duration_seconds=duration,
            stdout="",
            stderr=f"Script timed out after {timeout}s",
            exit_code=-1,
            error="timeout",
        )


def run_eval_script(eval_ws: Path, shared_ws: Path, eval_script: str = "eval.py", round_id: int = 0, timeout: int = 120) -> dict:
    """Run Evaluator's eval.py with cwd=eval_ws.

    eval.py reads from ./shared/dataset/ (via symlink) and writes metrics.json
    to ./shared/metrics.json. We read metrics from shared_ws/metrics.json.
    """
    full_path = eval_ws / eval_script
    metrics_path = shared_ws / "metrics.json"

    if not full_path.is_file():
        return {
            "coverage_estimate": 0.0,
            "confidence_interval": [0.0, 0.0],
            "coverage_by_dimension": {},
            "gaps": {},
            "error": "eval.py not found",
        }

    try:
        result = subprocess.run(
            [sys.executable, str(full_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(eval_ws),
        )
    except subprocess.TimeoutExpired:
        # eval.py took too long — write error to metrics.json so Evaluator sees it,
        # and return error dict so harness doesn't crash
        error_metrics = {
            "coverage_estimate": 0.0,
            "confidence_interval": [0.0, 0.0],
            "coverage_by_dimension": {},
            "gaps": {},
            "error": f"eval.py timed out after {timeout}s — verification incomplete, results from previous round may still be valid",
        }
        try:
            (shared_ws / "metrics.json").write_text(json.dumps(error_metrics, indent=2))
        except OSError:
            pass
        return error_metrics

    # Archive eval.py stdout/stderr per round
    log_dir = eval_ws / "cli_logs"
    log_dir.mkdir(exist_ok=True)
    prefix = f"r{round_id:02d}" if round_id > 0 else "r00"
    if result.stdout:
        (log_dir / f"{prefix}_eval_stdout.txt").write_text(result.stdout)
    if result.stderr:
        (log_dir / f"{prefix}_eval_stderr.txt").write_text(result.stderr)

    if result.returncode != 0:
        return {
            "coverage_estimate": 0.0,
            "confidence_interval": [0.0, 0.0],
            "coverage_by_dimension": {},
            "gaps": {},
            "error": f"eval.py failed: {result.stderr[-500:]}",
            "metrics_path": str(metrics_path),
        }

    # Read metrics.json from shared workspace
    if metrics_path.is_file():
        return json.loads(metrics_path.read_text())

    return {
        "coverage_estimate": 0.0,
        "error": "eval.py did not produce metrics.json",
    }
