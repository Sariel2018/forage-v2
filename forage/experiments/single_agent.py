"""Single Agent baseline: one Claude session, no harness.

This is what a user would normally do — give Claude a task and let it
freely iterate within one conversation. No structured evaluation,
no Evaluator/Planner separation, no formal coverage tracking.

The agent decides on its own when it's "done".
"""

import json
import subprocess
import tempfile
import time
from pathlib import Path

from ..core.spec import TaskSpec


def run_single_agent(
    spec: TaskSpec,
    output_dir: str = "output",
    timeout: int = 1800,  # 30 min max
) -> dict:
    """Run a single Claude session for the same task, no harness."""

    workspace = Path(tempfile.mkdtemp(prefix=f"forage_SA_{spec.name}_"))
    (workspace / "dataset").mkdir(exist_ok=True)

    results_dir = Path(output_dir) / spec.name
    results_dir.mkdir(parents=True, exist_ok=True)

    # Build prompt — same info as Forage gets, but no structured loop
    prompt = f"""You are given a data collection task. Complete it autonomously.

# Task
{spec.description}

# Details
- Topic: {spec.topic}
- Time range: {spec.time_range['start']} to {spec.time_range['end']}
- Document type: {spec.doc_type}
- Language: {spec.language}
- Seed sources: {spec.sources.seed_sources}

# Requirements
- Collect as many records as possible that match the task description
- Save collected data as JSONL files in the dataset/ directory
- Each record should have at minimum: title, url, date, full_text
- Deduplicate records
- When you believe you have collected all available data, stop and write a summary

# Budget
- You have {spec.budget.max_runtime_minutes} minutes maximum
- Be efficient with your time

# Output
When done, write a file called "summary.json" with:
{{
    "total_records": <number>,
    "sources_used": [<list of sources>],
    "coverage_estimate": "<your estimate of how complete the dataset is>",
    "gaps": "<what you think is missing, if anything>",
    "stop_reason": "<why you decided to stop>"
}}

Start now. Work in the current directory.
"""

    print(f"\n  SA workspace: {workspace}")
    print(f"  Running single agent (max {spec.budget.max_runtime_minutes} min)...")

    t0 = time.time()

    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "json",
        "--max-turns", "50",
        "--dangerously-skip-permissions",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(workspace),
        )
        duration = time.time() - t0

        # Parse output
        output = {}
        if result.stdout.strip():
            try:
                output = json.loads(result.stdout)
            except json.JSONDecodeError:
                output = {"result": result.stdout[-2000:]}

        # Count records in dataset/
        total_records = 0
        dataset_dir = workspace / "dataset"
        if dataset_dir.is_dir():
            for f in dataset_dir.glob("*.jsonl"):
                total_records += sum(1 for _ in open(f))

        # Read agent's self-reported summary
        summary_path = workspace / "summary.json"
        agent_summary = {}
        if summary_path.is_file():
            try:
                agent_summary = json.loads(summary_path.read_text())
            except json.JSONDecodeError:
                pass

        run_result = {
            "group": "SA",
            "total_records": total_records,
            "agent_self_report": agent_summary,
            "duration_seconds": duration,
            "cost_usd": output.get("total_cost_usd", 0.0),
            "usage": output.get("usage", {}),
            "stop_reason": agent_summary.get("stop_reason", "unknown"),
        }

    except subprocess.TimeoutExpired:
        duration = time.time() - t0
        total_records = 0
        dataset_dir = workspace / "dataset"
        if dataset_dir.is_dir():
            for f in dataset_dir.glob("*.jsonl"):
                total_records += sum(1 for _ in open(f))

        run_result = {
            "group": "SA",
            "total_records": total_records,
            "duration_seconds": duration,
            "error": "timeout",
            "stop_reason": "timeout",
        }

    # Copy workspace to results
    import shutil
    sa_dir = results_dir / "workspace"
    if sa_dir.exists():
        shutil.rmtree(sa_dir)
    shutil.copytree(workspace, sa_dir)

    # Save result
    with open(results_dir / "run_result.json", "w") as f:
        json.dump(run_result, f, indent=2, default=str)

    print(f"  SA done: {total_records} records in {duration:.0f}s")
    return run_result
