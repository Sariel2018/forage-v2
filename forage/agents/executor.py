"""Executor: runs the action script produced by the Planner.

Unlike Evaluator and Planner, the Executor is NOT an LLM agent.
It simply runs action.py and monitors execution (timeout, request budget, errors).
This keeps execution deterministic and auditable.
"""

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


def execute_collection(
    workspace: Path,
    script_path: str = "action.py",
    timeout: int = 1800,  # 30 min default
) -> ExecutionResult:
    """Run the collection script and return results.

    The script is expected to:
    - Save JSONL files to workspace/dataset/
    - Print a summary line: FORAGE_RESULT:{"records": N, "requests": M}
    """
    full_path = workspace / script_path
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

    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(full_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workspace),
        )
        duration = time.time() - t0

        # Parse result summary from stdout
        records = 0
        requests = 0
        for line in result.stdout.splitlines():
            if line.startswith("FORAGE_RESULT:"):
                import json
                try:
                    data = json.loads(line[len("FORAGE_RESULT:"):])
                    records = data.get("records", 0)
                    requests = data.get("requests", 0)
                except json.JSONDecodeError:
                    pass

        # If no FORAGE_RESULT line, count files in dataset/ only
        if records == 0:
            dataset_dir = workspace / "dataset"
            if dataset_dir.is_dir():
                for f in dataset_dir.rglob("*.jsonl"):
                    try:
                        with open(f) as fh:
                            records += sum(1 for _ in fh)
                    except (OSError, UnicodeDecodeError):
                        pass
                if records == 0:
                    for f in dataset_dir.rglob("*.json"):
                        records += 1

        return ExecutionResult(
            records_collected=records,
            requests_used=requests,
            duration_seconds=duration,
            stdout=result.stdout[-5000:],  # keep last 5K chars
            stderr=result.stderr[-2000:],
            exit_code=result.returncode,
        )

    except subprocess.TimeoutExpired:
        duration = time.time() - t0
        # Count records already written to dataset/ before timeout
        records = 0
        dataset_dir = workspace / "dataset"
        if dataset_dir.is_dir():
            for f in dataset_dir.rglob("*.jsonl"):
                try:
                    with open(f) as fh:
                        records += sum(1 for _ in fh)
                except (OSError, UnicodeDecodeError):
                    pass
        return ExecutionResult(
            records_collected=records,
            requests_used=0,
            duration_seconds=duration,
            stdout="",
            stderr=f"Script timed out after {timeout}s",
            exit_code=-1,
            error="timeout",
        )


def run_eval_script(workspace: Path, eval_script: str = "eval.py") -> dict:
    """Run eval.py deterministically (no LLM) and return metrics.

    eval.py should write metrics.json to the workspace.
    """
    full_path = workspace / eval_script
    if not full_path.is_file():
        return {
            "coverage_estimate": 0.0,
            "confidence_interval": [0.0, 0.0],
            "coverage_by_dimension": {},
            "gaps": {},
            "error": "eval.py not found",
        }

    result = subprocess.run(
        [sys.executable, str(full_path)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(workspace),
    )

    if result.returncode != 0:
        return {
            "coverage_estimate": 0.0,
            "confidence_interval": [0.0, 0.0],
            "coverage_by_dimension": {},
            "gaps": {},
            "error": f"eval.py failed: {result.stderr[-500:]}",
        }

    # Read metrics.json
    metrics_path = workspace / "metrics.json"
    if metrics_path.is_file():
        import json
        return json.loads(metrics_path.read_text())

    return {
        "coverage_estimate": 0.0,
        "error": "eval.py did not produce metrics.json",
    }
