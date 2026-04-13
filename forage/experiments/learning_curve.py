# forage/experiments/learning_curve.py
"""Learning curve experiment: run M+ on the same task multiple times,
accumulating knowledge between runs."""

import json
import shutil
import time
from pathlib import Path

from ..core.spec import TaskSpec
from ..core.loop import run
from ..core.knowledge import regenerate_index


def run_learning_curve(
    spec: TaskSpec,
    num_runs: int = 6,
    output_dir: str = "experiments",
    knowledge_dir: str | None = None,
    group: str = "M+",
    repeat_id: int = 1,
):
    """Run a learning curve experiment.

    Args:
        spec: Task specification
        num_runs: Number of sequential runs (learning trajectory)
        output_dir: Base output directory
        knowledge_dir: Path to knowledge/ directory (M+ starts empty, M uses static)
        group: "M+" (accumulating), "M" (static), "M-exp" (no knowledge)
        repeat_id: Which repeat this is (1, 2, 3...). Each repeat gets its own
                   directory and independent knowledge accumulation.
    """
    exp_dir = Path(output_dir) / spec.name / group / f"repeat_{repeat_id:02d}"
    exp_dir.mkdir(parents=True, exist_ok=True)

    # Save task spec to experiment directory for reference
    import yaml
    spec_record = {
        "task": {"name": spec.name, "description": spec.description, "task_type": spec.task_type},
        "budget": {
            "max_rounds": spec.budget.max_rounds,
            "max_turns_per_agent": spec.budget.max_turns_per_agent,
            "effort": spec.budget.effort,
            "max_requests": spec.budget.max_requests,
            "max_runtime_minutes": spec.budget.max_runtime_minutes,
        },
        "coverage": {"target": spec.coverage.target, "mode": spec.coverage.mode},
    }
    with open(exp_dir / "task_spec.yaml", "w") as f:
        yaml.dump(spec_record, f, default_flow_style=False, allow_unicode=True)

    # For M+: use accumulating knowledge (create empty if first run)
    if group == "M+":
        work_knowledge = exp_dir / "knowledge"
        if not work_knowledge.exists():
            work_knowledge.mkdir(parents=True)
            (work_knowledge / "universal").mkdir(exist_ok=True)
            (work_knowledge / "web_scraping").mkdir(exist_ok=True)
            (work_knowledge / "api").mkdir(exist_ok=True)
            regenerate_index(work_knowledge)
        active_knowledge = str(work_knowledge)
    elif group == "M":
        active_knowledge = knowledge_dir  # static, never changes
    else:  # M-exp
        active_knowledge = None

    # Load existing results if resuming
    results_file = exp_dir / "learning_curve.json"
    if results_file.exists():
        results = json.loads(results_file.read_text())
    else:
        results = []

    # Auto-detect starting run number from completed results (not just directories)
    start_run = len(results) + 1

    if start_run > num_runs:
        print(f"  Already completed {start_run - 1} runs (target: {num_runs}). Nothing to do.")
        return results

    for run_id in range(start_run, num_runs + 1):
        run_dir = exp_dir / f"run_{run_id:03d}"
        print(f"\n{'#'*60}")
        print(f"# Learning Curve: {spec.name} | {group} | Run {run_id}/{num_runs}")
        print(f"{'#'*60}")

        t0 = time.time()
        history = run(
            spec=spec,
            output_dir=str(run_dir),
            knowledge_dir=active_knowledge,
            mode="full",
            enable_post_mortem=(group == "M+"),
        )
        duration = time.time() - t0

        # Collect results
        if history:
            last = history[-1]
            run_result = {
                "run_id": run_id,
                "coverage": last.metrics.get("coverage_estimate", 0),
                "records_total": last.records_total,
                "denominator": last.metrics.get("denominator", "unknown"),
                "cost_usd": sum(r.cost_usd for r in history),
                "rounds": len(history),
                "duration_seconds": duration,
            }
        else:
            run_result = {
                "run_id": run_id,
                "coverage": 0,
                "records_total": 0,
                "denominator": "unknown",
                "cost_usd": 0,
                "rounds": 0,
                "duration_seconds": duration,
            }
        results.append(run_result)

        # Save incremental results
        with open(exp_dir / "learning_curve.json", "w") as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n  Run {run_id} complete: coverage={run_result['coverage']:.1%}, "
              f"cost=${run_result['cost_usd']:.2f}")

        if group == "M+":
            # Count knowledge entries
            k_count = sum(1 for _ in Path(active_knowledge).rglob("*.md")
                         if _.name != "INDEX.md")
            print(f"  Knowledge entries: {k_count}")

    # Write summary
    _write_learning_summary(results, exp_dir, group)
    return results


def _write_learning_summary(results: list, exp_dir: Path, group: str):
    """Write a markdown summary of the learning curve."""
    lines = [f"# Learning Curve Summary -- {group}\n"]
    lines.append("| Run | Coverage | Records | Denominator | Cost | Rounds |")
    lines.append("|-----|----------|---------|-------------|------|--------|")
    for r in results:
        cov = r['coverage']
        cov_str = f"{cov:.1%}" if isinstance(cov, (int, float)) else str(cov)
        lines.append(
            f"| {r['run_id']} | {cov_str} | {r['records_total']} | "
            f"{r['denominator']} | ${r['cost_usd']:.2f} | {r['rounds']} |"
        )
    (exp_dir / "summary.md").write_text("\n".join(lines))
