"""Forage outer loop v2: the harness that orchestrates co-evolving evaluation.

v2 changes (2026-04-03):
- Evaluator is auditor + stop decision maker (Selector removed)
- Method isolation: eval.py hidden from Planner, collect.py hidden from Evaluator
- Richer context: denominator history, strategy summaries, discoveries
- No keep/discard: data accumulates, eval.py handles dedup
- Evaluator runs eval.py internally within its LLM call

v2 loop restructure:
- Agents created once per run (explorer team mode with persistent sessions)
- Post-mortem phase: agents extract transferable lessons after run completes
- Trajectory persistence: structured per-round data saved as JSON
"""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .spec import TaskSpec
from .trajectory import Trajectory
from ..agents.evaluator import EvaluatorAgent
from ..agents.planner import PlannerAgent
from ..agents.executor import execute_collection, run_eval_script


@dataclass
class RoundResult:
    """Result of a single collection round."""

    round_id: int
    strategy: dict
    records_collected: int
    records_total: int
    metrics: dict
    eval_script_version: str
    duration_seconds: float
    decision: str  # "continue" | "stop"
    cost_usd: float
    usage: dict


def run(
    spec: TaskSpec,
    output_dir: str = "output",
    knowledge_dir: str | None = None,
    mode: str = "full",  # "full" | "no_isolation" | "freeze_eval" | "no_eval"
) -> list[RoundResult]:
    """Main Forage loop v2.

    Modes:
      full         — Evaluator + Planner with method isolation (M, M-exp groups)
      no_isolation — Evaluator + Planner without method isolation (M-no-iso group)
      freeze_eval  — Evaluator runs only Round 1, frozen after (M-co-eval group)
      no_eval      — No independent Evaluator, Planner self-evaluates (M-no-eval group)
    """
    import tempfile
    import sys
    workspace = Path(tempfile.mkdtemp(prefix=f"forage_{spec.name}_"))
    (workspace / "dataset").mkdir(exist_ok=True)

    results_dir = Path(output_dir) / spec.name
    results_dir.mkdir(parents=True, exist_ok=True)

    # v2: tee stdout to forage.log for persistence
    log_path = results_dir / "forage.log"
    _log_tee = _LogTee(log_path)
    sys.stdout = _log_tee

    try:
        return _run_inner(spec, workspace, results_dir, knowledge_dir, mode, log_path)
    finally:
        sys.stdout = _log_tee.terminal
        _log_tee.close()


def _run_inner(spec, workspace, results_dir, knowledge_dir, mode, log_path):
    """Inner run body — separated so stdout tee is always restored via try/finally."""
    from datetime import datetime, timezone

    history: list[RoundResult] = []
    total_cost_usd = 0.0
    metrics = {"coverage_estimate": 0.0, "total_collected": 0, "denominator": 0}
    eval_result_history: list[dict] = []
    planner_summaries: list[dict] = []

    # v2: create agents ONCE per run (explorer team mode)
    evaluator = EvaluatorAgent(workspace=str(workspace), knowledge_dir=knowledge_dir)
    planner = PlannerAgent(workspace=str(workspace), knowledge_dir=knowledge_dir)

    # v2: stage knowledge files to workspace
    if knowledge_dir:
        _stage_knowledge(knowledge_dir, workspace, spec)

    # v2: trajectory tracking
    trajectory = Trajectory(spec.name, {
        "name": spec.name,
        "description": spec.description,
        "topic": spec.topic,
        "coverage_target": spec.coverage.target,
    })
    trajectory.data["started_at"] = datetime.now(timezone.utc).isoformat()

    print(f"  Isolated workspace: {workspace}")

    print(f"\n{'#'*60}")
    print(f"# Forage v2: {spec.name}")
    print(f"# Topic: {spec.topic}")
    print(f"# Coverage target: {spec.coverage.target:.0%} ({spec.coverage.mode})")
    print(f"# Budget: {spec.budget.max_rounds} rounds | Mode: {mode}")
    print(f"{'#'*60}")

    for round_id in range(1, spec.budget.max_rounds + 1):
        t0 = time.time()
        round_cost = 0.0
        round_usage = {"input_tokens": 0, "output_tokens": 0}
        eval_result = {}
        strategy = {}

        print(f"\n{'='*60}")
        print(f"  Round {round_id}/{spec.budget.max_rounds}")
        print(f"{'='*60}")

        # --- Step 1: Evaluator ---
        should_stop = False

        if mode == "no_eval":
            # M-no-eval: skip independent Evaluator entirely
            print("\n  [1/3] Evaluator: SKIPPED (no-eval mode, Planner self-evaluates)")

        elif mode == "freeze_eval" and round_id > 1 and (workspace / "eval.py").is_file():
            # M-co-eval: frozen after Round 1
            print("\n  [1/3] Evaluator: FROZEN (using round 1 eval.py)")
            metrics = run_eval_script(workspace, "eval.py")
            if metrics.get("error"):
                print(f"         ERROR: eval.py failed: {metrics['error']}")
            coverage = _safe_coverage(metrics)
            print(f"         Coverage: {coverage:.1%}")
            # Hardcoded stop for frozen mode
            if coverage >= spec.coverage.target:
                should_stop = True
                print(f"         Decision: STOP (target reached)")

        else:
            # Full mode: run Evaluator
            label = "exploring data universe" if round_id == 1 else "auditing results"
            print(f"\n  [1/3] Evaluator: {label}...")

            # METHOD ISOLATION: hide collect.py before calling Evaluator (skip in no_isolation mode)
            if mode != "no_isolation":
                _hide_file(workspace / "collect.py")

            eval_context = _build_evaluator_context(
                spec, history, workspace, eval_result_history, planner_summaries,
            )
            eval_result = evaluator.run_with_recovery(eval_context, trajectory=trajectory)
            round_cost += evaluator.cost_usd
            _merge_usage(round_usage, evaluator.usage)

            # Restore collect.py
            if mode != "no_isolation":
                _restore_file(workspace / "collect.py")

            if eval_result.get("error"):
                print(f"         ERROR: {eval_result['error']}")
                if eval_result.get("stderr"):
                    print(f"         STDERR: {eval_result['stderr'][:500]}")
                print(f"         Skipping this round (agent call failed)")
                continue

            # Check if Evaluator returned a meaningful result
            if "denominator" not in eval_result and "eval_script_path" not in eval_result and "text" in eval_result:
                # Evaluator didn't return JSON, but check if it wrote eval.py anyway
                if (workspace / "eval.py").is_file():
                    print(f"         WARNING: Evaluator returned text instead of JSON, but eval.py exists — proceeding with defaults")
                    eval_result = {
                        "eval_script_path": "eval.py",
                        "denominator": "unknown",
                        "denominator_source": "unknown",
                        "denominator_confidence": "low",
                        "decision": "continue",
                        "decision_reason": "Evaluator did not return structured response, proceeding with eval.py found in workspace",
                    }
                else:
                    print(f"         WARNING: Evaluator returned unstructured text and no eval.py found")
                    print(f"         Text preview: {str(eval_result.get('text', ''))[:200]}")
                    print(f"         Skipping this round")
                    continue

            # Track Evaluator's output
            eval_result_history.append({
                "round": round_id,
                "denominator": eval_result.get("denominator", "unknown"),
                "denominator_source": eval_result.get("denominator_source", "?"),
                "denominator_confidence": eval_result.get("denominator_confidence", "?"),
                "discovery": eval_result.get("discovery", ""),
                "new_sources_found": eval_result.get("new_sources_found", []),
            })

            denominator = eval_result.get("denominator", "unknown")
            decision = eval_result.get("decision", "continue")
            print(f"         Denominator: {denominator}")
            print(f"         Decision: {decision} — {eval_result.get('decision_reason', '?')}")

            if decision == "stop":
                should_stop = True

            # Read latest metrics from workspace (Evaluator may have run eval.py internally)
            metrics_path = workspace / "metrics.json"
            if metrics_path.is_file():
                try:
                    metrics = json.loads(metrics_path.read_text())
                except json.JSONDecodeError:
                    pass

        # Check stop before Planner
        if should_stop:
            coverage = _safe_coverage(metrics)
            duration = time.time() - t0
            total_cost_usd += round_cost
            records_total = _count_total_records(workspace)
            result = RoundResult(
                round_id=round_id, strategy={}, records_collected=0,
                records_total=records_total, metrics=metrics,
                eval_script_version="eval.py", duration_seconds=duration,
                decision="stop", cost_usd=round_cost, usage=round_usage,
            )
            history.append(result)
            with open(results_dir / "history.jsonl", "a") as f:
                f.write(json.dumps(asdict(result), default=str) + "\n")

            # v2: record trajectory for early-stop round
            trajectory.add_round({
                "round_id": round_id,
                "duration_seconds": duration,
                "denominator": eval_result.get("denominator", "unknown"),
                "denominator_source": eval_result.get("denominator_source", "?"),
                "denominator_confidence": eval_result.get("denominator_confidence", "?"),
                "discovery": eval_result.get("discovery", ""),
                "evaluator_decision": "stop",
                "evaluator_airdropped": eval_result.get("_airdropped", False),
                "strategy_name": "N/A",
                "target_source": "N/A",
                "strategy_description": "Stopped before planning",
                "planner_airdropped": False,
                "records_collected": 0,
                "records_total": records_total,
                "coverage": coverage,
                "error_count": 0,
                "exit_code": -1,
                "knowledge_files_read": {},
                "round_cost_usd": round_cost,
            })

            print(f"\n  STOPPING: {eval_result.get('decision_reason', 'target reached')}")
            break

        # --- Step 2: Planner ---
        print("\n  [2/3] Planner: proposing strategy...")

        # METHOD ISOLATION: hide eval.py before calling Planner (skip in no_isolation mode)
        if mode != "no_isolation":
            _hide_file(workspace / "eval.py")

        plan_context = _build_planner_context(
            spec, history, workspace, eval_result_history, mode,
        )
        plan_result = planner.run_with_recovery(plan_context, trajectory=trajectory)
        round_cost += planner.cost_usd
        _merge_usage(round_usage, planner.usage)

        # Restore eval.py
        if mode != "no_isolation":
            _restore_file(workspace / "eval.py")

        if plan_result.get("error"):
            print(f"         ERROR: {plan_result['error']}")
            if plan_result.get("stderr"):
                print(f"         STDERR: {plan_result['stderr'][:500]}")
            print(f"         Skipping this round (agent call failed)")
            continue

        if "strategy_name" not in plan_result and "collect_script_path" not in plan_result and "text" in plan_result:
            print(f"         WARNING: Planner returned unstructured text, no JSON found")
            print(f"         Text preview: {str(plan_result.get('text', ''))[:200]}")
            print(f"         Skipping this round")
            continue

        strategy = plan_result
        print(f"         Strategy: {strategy.get('strategy_name', '?')}")

        # Track Planner summary for Evaluator
        planner_summaries.append({
            "round": round_id,
            "strategy_name": strategy.get("strategy_name", "?"),
            "target_source": strategy.get("target_source", "?"),
            "strategy_description": strategy.get("strategy_description", "?"),
        })

        # M-no-eval: check Planner's self-assessed stop decision
        if mode == "no_eval" and strategy.get("decision") == "stop":
            should_stop = True

        # --- Step 3: Executor ---
        print("\n  [3/3] Executor: running collection script...")
        collect_script = strategy.get("collect_script_path", "collect.py")
        exec_result = execute_collection(
            workspace=workspace,
            script_path=collect_script,
            timeout=spec.budget.max_runtime_minutes * 60 // spec.budget.max_rounds,
        )
        print(f"         Collected: {exec_result.records_collected} records ({exec_result.duration_seconds:.0f}s)")

        if exec_result.error:
            print(f"         Error: {exec_result.error}")

        # --- Step 4: Run eval.py (deterministic, for next round's Evaluator) ---
        eval_script = "eval.py"
        if (workspace / eval_script).is_file():
            metrics = run_eval_script(workspace, eval_script)
        coverage = _safe_coverage(metrics)
        print(f"         Coverage: {coverage:.1%}")

        # Record results
        duration = time.time() - t0
        total_cost_usd += round_cost
        records_total = _count_total_records(workspace)

        result = RoundResult(
            round_id=round_id,
            strategy=strategy,
            records_collected=exec_result.records_collected,
            records_total=records_total,
            metrics=metrics,
            eval_script_version=eval_script,
            duration_seconds=duration,
            decision="stop" if should_stop else "continue",
            cost_usd=round_cost,
            usage=round_usage,
        )
        history.append(result)

        with open(results_dir / "history.jsonl", "a") as f:
            f.write(json.dumps(asdict(result), default=str) + "\n")

        # v2: record trajectory
        trajectory.add_round({
            "round_id": round_id,
            "duration_seconds": duration,
            "denominator": eval_result.get("denominator", "unknown"),
            "denominator_source": eval_result.get("denominator_source", "?"),
            "denominator_confidence": eval_result.get("denominator_confidence", "?"),
            "discovery": eval_result.get("discovery", ""),
            "evaluator_decision": "stop" if should_stop else "continue",
            "evaluator_airdropped": eval_result.get("_airdropped", False),
            "strategy_name": strategy.get("strategy_name", "?"),
            "target_source": strategy.get("target_source", "?"),
            "strategy_description": strategy.get("strategy_description", "?"),
            "planner_airdropped": strategy.get("_airdropped", False),
            "records_collected": exec_result.records_collected if exec_result else 0,
            "records_total": records_total,
            "coverage": _safe_coverage(metrics),
            "error_count": (1 if exec_result.error else 0) if exec_result else 0,
            "exit_code": exec_result.exit_code if exec_result else -1,
            "knowledge_files_read": {},
            "round_cost_usd": round_cost,
        })

        print(f"\n  >> Records: {records_total} | Coverage: {coverage:.1%} | Time: {duration:.0f}s")

        if should_stop:
            print(f"\n  STOPPING: Planner decided to stop")
            break

    # v2: save trajectory
    trajectory.data["ended_at"] = datetime.now(timezone.utc).isoformat()
    trajectory.set_final_state({
        "decision": history[-1].decision if history else "unknown",
        "final_coverage": _safe_coverage(metrics),
        "final_denominator": metrics.get("denominator", "unknown"),
        "final_records": _count_total_records(workspace),
    })
    trajectory.save(results_dir / "trajectory.json")

    # v2: post-mortem phase (only for "full" mode with knowledge_dir)
    if mode == "full" and knowledge_dir:
        pm_cost = _run_post_mortem(evaluator, planner, trajectory, knowledge_dir, workspace, results_dir)
        total_cost_usd += pm_cost
        trajectory.data["total_cost_usd"] += pm_cost

    # --- Final: copy workspace artifacts to results_dir ---
    import shutil
    artifacts_dir = results_dir / "workspace"
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)
    shutil.copytree(workspace, artifacts_dir)
    # Note: NOT cleaning up temp workspace — useful for debugging.
    # Old workspaces accumulate in /tmp/ but OS cleans on reboot.

    _write_final_outputs(history, metrics, total_cost_usd, results_dir, artifacts_dir)

    # v2: auto-generate HTML report
    from ..report import generate_report
    generate_report(results_dir / "trajectory.json")
    print(f"  Workspace copied to: {artifacts_dir}")
    print(f"  Log saved to: {log_path}")

    return history


# --- Log tee ---


class _LogTee:
    """Tee stdout to both terminal and a log file (real-time flush)."""

    def __init__(self, log_path: Path):
        import sys
        self.terminal = sys.stdout
        self.log = open(log_path, "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
        self.log.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()

    def close(self):
        self.log.close()


# --- Context builders ---


def _build_evaluator_context(
    spec: TaskSpec,
    history: list[RoundResult],
    workspace: Path | None,
    eval_result_history: list[dict],
    planner_summaries: list[dict],
) -> str:
    """Build the user message for the Evaluator Agent."""
    round_id = len(history) + 1
    parts = [
        f"# Task: {spec.description}",
        f"Topic: {spec.topic}",
        f"Time range: {spec.time_range['start']} to {spec.time_range['end']}",
        f"Document type: {spec.doc_type}",
        f"Language: {spec.language}",
        f"Coverage target: {spec.coverage.target:.0%} ({spec.coverage.mode})",
        f"Coverage dimensions: {spec.coverage.dimensions}",
        f"Seed sources: {spec.sources.seed_sources}",
        f"Preferred sources: {spec.sources.preferred_sources}",
        f"\nRound: {round_id}",
    ]

    if round_id == 1:
        parts.append("\nThis is Round 1. Please explore data sources, define the initial denominator, and write eval.py.")
    else:
        parts.append("\nThis is Round 2+. Please audit the previous results and decide whether to continue.")

        # Previous metrics
        if history:
            last = history[-1]
            parts.append(f"\nPrevious round coverage: {_safe_coverage(last.metrics):.1%}")
            parts.append(f"Total records so far: {last.records_total}")
            if last.metrics.get("gaps"):
                parts.append(f"Gaps:\n{json.dumps(last.metrics['gaps'], indent=2)}")

        # Denominator history
        if eval_result_history:
            parts.append("\nDenominator history:")
            for e in eval_result_history:
                parts.append(f"  R{e['round']}: {e['denominator']} (source: {e.get('denominator_source', '?')}, confidence: {e.get('denominator_confidence', '?')})")

        # Previous eval.py content summary
        if workspace and (workspace / "eval.py").is_file():
            eval_content = (workspace / "eval.py").read_text()
            lines = eval_content.splitlines()[:80]
            parts.append(f"\nYour previous eval.py (first {len(lines)} lines):\n```python\n" + "\n".join(lines) + "\n```")

        # Planner strategy summaries
        if planner_summaries:
            parts.append("\nPlanner strategy summaries (what methods were used — you cannot see their code):")
            for ps in planner_summaries:
                parts.append(f"  R{ps['round']}: {ps['strategy_name']} → {ps.get('target_source', '?')}")

    # Format reminder (prevents drift in persistent sessions)
    parts.append("\n## IMPORTANT: Output format")
    parts.append("Respond with a JSON object containing: denominator, denominator_source, denominator_confidence, discovery, decision, decision_reason.")
    parts.append("Write eval.py to the workspace before responding.")

    return "\n".join(parts)


def _build_planner_context(
    spec: TaskSpec,
    history: list[RoundResult],
    workspace: Path,
    eval_result_history: list[dict],
    mode: str,
) -> str:
    """Build the user message for the Planner Agent."""
    parts = [
        f"# Task: {spec.description}",
        f"Topic: {spec.topic}",
        f"Time range: {spec.time_range['start']} to {spec.time_range['end']}",
        f"Document type: {spec.doc_type}",
        f"Seed sources: {spec.sources.seed_sources}",
        f"Preferred sources: {spec.sources.preferred_sources}",
        f"Rate limit: {spec.risk.max_requests_per_minute} req/min",
        f"\nRound: {len(history) + 1}",
    ]

    # Include metrics from eval.py if available
    metrics_path = workspace / "metrics.json"
    if metrics_path.is_file():
        try:
            m = json.loads(metrics_path.read_text())
            parts.append(f"\nCurrent metrics:\n{json.dumps(m, indent=2)}")
        except json.JSONDecodeError:
            pass

    # Evaluator discoveries (new data sources found)
    if eval_result_history:
        latest = eval_result_history[-1]
        if latest.get("discovery"):
            parts.append(f"\nEvaluator discovery: {latest['discovery']}")
        if latest.get("new_sources_found"):
            parts.append(f"New data sources found: {latest['new_sources_found']}")

    # Previous strategy history
    if history:
        parts.append("\nPrevious strategies:")
        for h in history:
            parts.append(
                f"  Round {h.round_id}: {h.strategy.get('strategy_name', '?')} "
                f"→ {h.records_collected} records, coverage {_safe_coverage(h.metrics):.1%}"
            )

    # M-no-eval mode: Planner also handles evaluation
    if mode == "no_eval":
        parts.append("\n## Additional responsibility (no independent Evaluator):")
        parts.append("You must also write eval.py — a deterministic Python script that:")
        parts.append("- Reads collected data from dataset/ directory")
        parts.append("- Defines and estimates the coverage denominator (total records that should exist)")
        parts.append("- Outputs metrics.json with AT MINIMUM these fields:")
        parts.append("  - coverage_estimate (float, 0.0-1.0): collected / denominator")
        parts.append("  - total_collected (int): number of records in dataset/")
        parts.append("  - denominator (int): estimated total records that exist")
        parts.append("- May also include: coverage_by_dimension, gaps, quality metrics")
        parts.append("You must also decide whether to stop or continue collecting.")
        parts.append("Add to your output JSON: \"decision\": \"continue\" or \"stop\", \"decision_reason\": \"...\"")

    parts.append("\nPropose a collection strategy and write collect.py.")

    # Format reminder (prevents drift in persistent sessions)
    parts.append("\n## IMPORTANT: Output format")
    parts.append("Respond with a JSON object containing: strategy_name, strategy_description, target_source, expected_records, collect_script_path.")

    return "\n".join(parts)


# --- Method isolation ---


def _hide_file(path: Path):
    """Hide a file by prefixing with dot (method isolation)."""
    if path.is_file():
        hidden = path.parent / f".{path.name}"
        path.rename(hidden)


def _restore_file(path: Path):
    """Restore a hidden file."""
    hidden = path.parent / f".{path.name}"
    if hidden.is_file():
        hidden.rename(path)


# --- Helpers ---


def _safe_coverage(metrics: dict) -> float:
    """Safely extract coverage as a float, handling unexpected types."""
    cov = metrics.get("coverage_estimate", 0.0)
    if isinstance(cov, (int, float)):
        return float(cov)
    return 0.0


def _merge_usage(target: dict, source: dict):
    """Merge token usage counters from a single agent call into the round total."""
    for key in ["input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"]:
        if key in source:
            target[key] = target.get(key, 0) + source[key]


def _count_total_records(workspace: Path) -> int:
    """Count total records, searching recursively for both .jsonl and .json files."""
    total = 0
    for f in workspace.rglob("*.jsonl"):
        try:
            with open(f) as fh:
                total += sum(1 for _ in fh)
        except (OSError, UnicodeDecodeError):
            pass
    if total == 0:
        for f in workspace.rglob("*.json"):
            if f.name in ("metrics.json", "summary.json"):
                continue
            total += 1
    return total


def _stage_knowledge(knowledge_dir: str, workspace: Path, spec: TaskSpec):
    """Copy relevant knowledge files to agent workspace (v2)."""
    import shutil
    src = Path(knowledge_dir)
    dst = workspace / "knowledge"
    dst.mkdir(exist_ok=True)

    # Always copy universal/
    if (src / "universal").exists():
        shutil.copytree(src / "universal", dst / "universal", dirs_exist_ok=True)

    # Copy task-type-specific scope
    task_type = getattr(spec, 'task_type', 'web_scraping')
    if task_type and (src / task_type).exists():
        shutil.copytree(src / task_type, dst / task_type, dirs_exist_ok=True)

    # Copy INDEX.md
    if (src / "INDEX.md").exists():
        shutil.copy(src / "INDEX.md", dst / "INDEX.md")


def _run_post_mortem(evaluator, planner, trajectory, knowledge_dir, workspace, results_dir):
    """Run post-mortem: each agent extracts lessons from the run (v2)."""
    from .knowledge import write_knowledge_entry, regenerate_index

    knowledge_path = Path(knowledge_dir)

    print("\n  [Post-Mortem] Evaluator extracting lessons...")
    eval_narrative = trajectory.render_narrative(view="evaluator")
    eval_pm_message = (
        f"# Post-Mortem\n\n"
        f"The task is complete. Here is your trajectory:\n\n"
        f"{eval_narrative}\n\n"
        f"{evaluator.post_mortem_prompt}"
    )
    eval_lessons = evaluator.run(eval_pm_message)
    pm_cost = evaluator.cost_usd

    print("  [Post-Mortem] Planner extracting lessons...")
    plan_narrative = trajectory.render_narrative(view="planner")
    plan_pm_message = (
        f"# Post-Mortem\n\n"
        f"The task is complete. Here is your trajectory:\n\n"
        f"{plan_narrative}\n\n"
        f"{planner.post_mortem_prompt}"
    )
    plan_lessons = planner.run(plan_pm_message)
    pm_cost += planner.cost_usd

    # Extract and write lessons
    all_lessons = []
    for lessons_result in [eval_lessons, plan_lessons]:
        if isinstance(lessons_result, dict) and "items" in lessons_result:
            all_lessons.extend(lessons_result["items"])
        elif isinstance(lessons_result, list):
            all_lessons.extend(lessons_result)

    for lesson in all_lessons:
        if isinstance(lesson, dict) and "id" in lesson:
            write_knowledge_entry(knowledge_path, lesson)

    # Regenerate INDEX
    if all_lessons:
        regenerate_index(knowledge_path)

    # Save knowledge snapshot
    import shutil
    snapshot_dir = results_dir / "knowledge_snapshot"
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    shutil.copytree(knowledge_path, snapshot_dir)

    print(f"\n  Post-mortem: extracted {len(all_lessons)} lessons, cost=${pm_cost:.2f}")
    return pm_cost


def _write_final_outputs(
    history: list[RoundResult],
    final_metrics: dict,
    total_cost_usd: float,
    results_dir: Path,
    workspace: Path,
):
    """Write deliverables: metrics.json, gaps.md, summary.md."""
    total_usage = {}
    for h in history:
        _merge_usage(total_usage, h.usage)

    output_metrics = {
        **final_metrics,
        "total_rounds": len(history),
        "total_cost_usd": total_cost_usd,
        "total_usage": total_usage,
        "total_records": history[-1].records_total if history else 0,
    }
    with open(results_dir / "metrics.json", "w") as f:
        json.dump(output_metrics, f, indent=2, default=str)

    gaps = final_metrics.get("gaps", {})
    with open(results_dir / "gaps.md", "w") as f:
        f.write("# Gap Report\n\n")
        f.write(f"**Final coverage**: {_safe_coverage(final_metrics):.1%}\n\n")
        if not gaps:
            f.write("No gaps detected. Target coverage reached.\n")
        else:
            if isinstance(gaps, dict):
                for key, value in gaps.items():
                    f.write(f"## {key}\n\n{value}\n\n")
            else:
                f.write(str(gaps))

    with open(results_dir / "summary.md", "w") as f:
        f.write("# Forage Run Summary\n\n")
        f.write("| Round | Strategy | Records | Coverage | Decision |\n")
        f.write("|-------|----------|---------|----------|----------|\n")
        for h in history:
            f.write(
                f"| {h.round_id} | {h.strategy.get('strategy_name', '?')} "
                f"| {h.records_collected} | {_safe_coverage(h.metrics):.1%} "
                f"| {h.decision} |\n"
            )
        f.write(f"\n**Total records**: {history[-1].records_total if history else 0}\n")
        f.write(f"**Total cost**: ${total_cost_usd:.4f}\n")

    print(f"\n  Outputs written:")
    print(f"    {results_dir / 'metrics.json'}")
    print(f"    {results_dir / 'gaps.md'}")
    print(f"    {results_dir / 'summary.md'}")
