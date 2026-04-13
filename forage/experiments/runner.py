"""Experiment runner v2.1: manages isolation, experiment groups, and repeats.

Experiment groups (6-group ablation chain):
  SA         — Single Agent baseline (one Claude session, no harness)
  M-no-eval  — Planner self-evaluates (no independent Evaluator)
  M-no-iso   — Two separate agents but no method isolation (can see each other's code)
  M-co-eval  — Evaluator frozen after round 1 (denominator blindness test)
  M-exp      — full Forage without experience knowledge base
  M          — full Forage with experience knowledge base
"""

import json
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from ..core.spec import TaskSpec, BudgetSpec
from ..core.loop import run
from .single_agent import run_single_agent


def run_experiment(
    spec: TaskSpec,
    groups: list[str],
    repeats: int = 3,
    output_dir: str = "experiments",
    knowledge_dir: str | None = None,
    parallel: bool = False,
):
    """Run comparative experiments across groups with isolation.

    Args:
        parallel: If True, run all groups in parallel (one process per group).
                  Repeats within a group are still sequential.
    """
    exp_dir = Path(output_dir) / spec.name
    exp_dir.mkdir(parents=True, exist_ok=True)

    if parallel:
        all_results = _run_parallel(spec, groups, repeats, exp_dir, knowledge_dir)
    else:
        all_results = _run_sequential(spec, groups, repeats, exp_dir, knowledge_dir)

    # Write comparative summary
    _write_comparison(all_results, exp_dir)


def _run_sequential(spec, groups, repeats, exp_dir, knowledge_dir):
    """Run groups one after another."""
    all_results = {}
    for group in groups:
        all_results[group] = _run_group(spec, group, repeats, exp_dir, knowledge_dir)
    return all_results


def _run_parallel(spec, groups, repeats, exp_dir, knowledge_dir):
    """Run groups in parallel, one process per group."""
    import multiprocessing as mp

    all_results = {}
    processes = {}

    for group in groups:
        # Each group runs in a separate process
        p = mp.Process(
            target=_run_group_and_save,
            args=(spec, group, repeats, str(exp_dir), knowledge_dir),
        )
        p.start()
        processes[group] = p
        print(f"  Started {group} in process {p.pid}")
        time.sleep(2)  # stagger starts to avoid simultaneous API hits

    # Wait for all to finish
    for group, p in processes.items():
        p.join()
        print(f"  {group} finished (exit code {p.exitcode})")

        # Read results from saved file
        result_file = exp_dir / group / "group_results.json"
        if result_file.is_file():
            all_results[group] = json.loads(result_file.read_text())
        else:
            all_results[group] = [{"group": group, "error": "process failed"}]

    return all_results


def _run_group_and_save(spec, group, repeats, exp_dir_str, knowledge_dir):
    """Run a group and save results to JSON (for parallel mode)."""
    exp_dir = Path(exp_dir_str)
    results = _run_group(spec, group, repeats, exp_dir, knowledge_dir)
    result_file = exp_dir / group / "group_results.json"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    with open(result_file, "w") as f:
        json.dump(results, f, indent=2, default=str)


def _run_group(spec, group, repeats, exp_dir, knowledge_dir):
    """Run all repeats for a single experiment group."""
    print(f"\n{'#'*60}")
    print(f"# Experiment Group: {group}")
    print(f"{'#'*60}")

    group_results = []

    for rep in range(1, repeats + 1):
        print(f"\n--- {group} / Run {rep}/{repeats} ---")

        # Create isolated workspace (never delete old runs)
        run_dir = exp_dir / group / f"run_{rep:03d}"
        if run_dir.exists() and (run_dir / "run_result.json").exists():
            print(f"  Skipping {group}/run_{rep:03d} — already has results")
            continue
        if run_dir.exists():
            # Don't delete — create timestamped dir instead
            ts = time.strftime("%Y%m%d_%H%M%S")
            run_dir = exp_dir / group / f"run_{rep:03d}_{ts}"
        run_dir.mkdir(parents=True)

        # Copy spec into isolated workspace
        spec_copy = _configure_group(spec, group)
        _write_spec_to_dir(spec_copy, run_dir)

        # Determine knowledge visibility
        run_knowledge = None
        if group in ("M", "M-co-eval", "M-no-eval", "M-no-iso") and knowledge_dir:
            run_knowledge = str(run_dir / "knowledge")
            src = Path(knowledge_dir)
            if src.is_dir():
                shutil.copytree(src, run_knowledge)

        # Run experiment
        t0 = time.time()
        try:
            if group == "SA":
                sa_result = run_single_agent(
                    spec_copy,
                    output_dir=str(run_dir),
                    timeout=spec_copy.budget.max_runtime_minutes * 60,
                )
                duration = time.time() - t0
                run_result = {
                    "group": group,
                    "run": rep,
                    "rounds": 1,
                    "final_coverage": sa_result.get("agent_self_report", {}).get("coverage_estimate", "unknown"),
                    "total_records": sa_result.get("total_records", 0),
                    "total_cost_usd": sa_result.get("cost_usd", 0),
                    "duration_seconds": duration,
                    "stop_reason": sa_result.get("stop_reason", "unknown"),
                }
            else:
                # Determine mode based on group
                if group == "M-co-eval":
                    mode = "freeze_eval"
                elif group == "M-no-eval":
                    mode = "no_eval"
                elif group == "M-no-iso":
                    mode = "no_isolation"
                else:
                    mode = "full"

                history = run(
                    spec_copy,
                    output_dir=str(run_dir),
                    knowledge_dir=run_knowledge,
                    mode=mode,
                    enable_post_mortem=False,  # v1 runner doesn't accumulate knowledge
                )
                duration = time.time() - t0
                run_result = {
                    "group": group,
                    "run": rep,
                    "rounds": len(history),
                    "final_coverage": history[-1].metrics.get("coverage_estimate", 0) if history else 0,
                    "total_records": history[-1].records_total if history else 0,
                    "total_cost_usd": sum(h.cost_usd for h in history),
                    "duration_seconds": duration,
                    "stop_reason": _infer_stop_reason(history, spec_copy),
                }
        except Exception as e:
            duration = time.time() - t0
            run_result = {
                "group": group,
                "run": rep,
                "error": str(e),
                "duration_seconds": duration,
            }

        group_results.append(run_result)

        # Save individual run result
        with open(run_dir / "run_result.json", "w") as f:
            json.dump(run_result, f, indent=2, default=str)

        print(f"    Result: coverage={run_result.get('final_coverage', '?')}, records={run_result.get('total_records', '?')}")

    return group_results


def _configure_group(spec: TaskSpec, group: str) -> TaskSpec:
    """Adjust spec based on experiment group."""
    import copy
    s = copy.deepcopy(spec)

    if group == "B1":
        s.budget = BudgetSpec(
            max_rounds=1,
            max_runtime_minutes=s.budget.max_runtime_minutes,
            max_requests=s.budget.max_requests,
        )

    elif group == "M-exp":
        pass  # Full method, no knowledge — handled by not passing knowledge_dir

    elif group == "M":
        pass  # Full method with knowledge — handled by copying knowledge_dir

    elif group == "M-co-eval":
        pass  # TODO: implement eval freezing in loop

    elif group == "SA":
        pass  # Handled separately in _run_group

    return s


def _write_spec_to_dir(spec: TaskSpec, run_dir: Path):
    """Write spec as YAML to the isolated run directory."""
    import yaml
    spec_dict = {
        "task": {"name": spec.name, "description": spec.description, "task_type": spec.task_type},
        "target": {
            "topic": spec.topic,
            "time_range": spec.time_range,
            "doc_type": spec.doc_type,
            "language": spec.language,
        },
        "coverage": {
            "mode": spec.coverage.mode,
            "target": spec.coverage.target,
            "dimensions": spec.coverage.dimensions,
        },
        "quality": {
            "min_text_length": spec.quality.min_text_length,
            "required_fields": spec.quality.required_fields,
            "dedup": spec.quality.dedup,
        },
        "budget": {
            "max_rounds": spec.budget.max_rounds,
            "max_runtime_minutes": spec.budget.max_runtime_minutes,
            "max_requests": spec.budget.max_requests,
        },
        "risk": {
            "respect_robots_txt": spec.risk.respect_robots_txt,
            "max_requests_per_minute": spec.risk.max_requests_per_minute,
            "forbidden_sources": spec.risk.forbidden_sources,
        },
        "sources": {
            "seed_sources": spec.sources.seed_sources,
            "preferred_sources": spec.sources.preferred_sources,
            "forbidden_sources": spec.sources.forbidden_sources,
        },
    }
    with open(run_dir / "spec.yaml", "w") as f:
        yaml.dump(spec_dict, f, default_flow_style=False, allow_unicode=True)


def _safe_coverage(metrics: dict) -> float:
    cov = metrics.get("coverage_estimate", 0.0)
    return float(cov) if isinstance(cov, (int, float)) else 0.0


def _infer_stop_reason(history, spec) -> str:
    if not history:
        return "no_rounds"
    last = history[-1]
    # v2: check decision field from Evaluator/Planner
    if last.decision == "stop":
        return "evaluator_stop"
    coverage = _safe_coverage(last.metrics)
    if coverage >= spec.coverage.target:
        return "target_reached"
    actual_rounds = last.round_id if history else 0
    if actual_rounds >= spec.budget.max_rounds:
        return "budget_exhausted"
    return "unknown"


def _write_comparison(all_results: dict, exp_dir: Path):
    """Write a comparative summary across all groups."""

    with open(exp_dir / "comparison.md", "w") as f:
        f.write("# Experiment Comparison\n\n")
        f.write("| Group | Run | Rounds | Coverage | Records | Cost ($) | Time (s) | Stop Reason |\n")
        f.write("|-------|-----|--------|----------|---------|----------|----------|-------------|\n")

        for group, results in all_results.items():
            for r in results:
                cov = r.get('final_coverage', 0)
                cov_str = f"{cov:.1%}" if isinstance(cov, (int, float)) else str(cov)
                f.write(
                    f"| {r.get('group', '?')} "
                    f"| {r.get('run', '?')} "
                    f"| {r.get('rounds', '?')} "
                    f"| {cov_str} "
                    f"| {r.get('total_records', 0)} "
                    f"| {r.get('total_cost_usd', 0):.4f} "
                    f"| {r.get('duration_seconds', 0):.0f} "
                    f"| {r.get('stop_reason', '?')} |\n"
                )

        # Averages
        f.write("\n## Averages\n\n")
        f.write("| Group | Avg Coverage | Avg Records | Avg Cost ($) | Avg Time (s) |\n")
        f.write("|-------|-------------|-------------|-------------|-------------|\n")

        for group, results in all_results.items():
            valid = [r for r in results if "error" not in r]
            if valid:
                avg_cov = sum(r.get("final_coverage", 0) for r in valid if isinstance(r.get("final_coverage"), (int, float))) / max(len(valid), 1)
                avg_rec = sum(r.get("total_records", 0) for r in valid) / len(valid)
                avg_cost = sum(r.get("total_cost_usd", 0) for r in valid) / len(valid)
                avg_time = sum(r.get("duration_seconds", 0) for r in valid) / len(valid)
                f.write(f"| {group} | {avg_cov:.1%} | {avg_rec:.0f} | {avg_cost:.4f} | {avg_time:.0f} |\n")
            else:
                f.write(f"| {group} | ERROR | - | - | - |\n")

    # Also save raw JSON
    with open(exp_dir / "comparison.json", "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\n  Comparison written to {exp_dir / 'comparison.md'}")
