"""Forage outer loop v2: the harness that orchestrates co-evolving evaluation.

v2 changes (2026-04-03):
- Evaluator is auditor + stop decision maker (Selector removed)
- Method isolation: dual-workspace layout (eval_ws/plan_ws/shared) replaces
  the previous dotfile-hide trick (2026-04-14 refactor)
- Richer context: denominator history, strategy summaries, discoveries
- No keep/discard: data accumulates, eval.py handles dedup
- Evaluator runs eval.py internally within its LLM call

v2 loop restructure:
- Agents created once per run (explorer team mode with persistent sessions)
- Post-mortem phase: agents extract transferable lessons after run completes
- Trajectory persistence: structured per-round data saved as JSON

Workspace layout (v2, 2026-04-14):

    ws.root/
      eval_ws/        # Evaluator's private cwd (eval.py lives here)
        shared -> ../shared
      plan_ws/        # Planner's private cwd (action.py lives here)
        shared -> ../shared
      shared/         # Public contract surface; both agents see this
        dataset/
        metrics.json
        eval_contract.md
        knowledge/

Isolation is enforced architecturally: each agent only sees the other's work
through the shared directory. No more ``_hide_file`` / ``_restore_file``.
"""

import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from .spec import TaskSpec
from .trajectory import Trajectory
from .workspace import RunWorkspaces, build_run_workspaces, cleanup_workspaces
from ..agents.evaluator import EvaluatorAgent
from ..agents.planner import PlannerAgent
from ..agents.executor import ExecutionResult, execute_collection, run_eval_script


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
    enable_post_mortem: bool = True,
) -> list[RoundResult]:
    """Main Forage loop v2.

    Modes:
      full         — Evaluator + Planner with method isolation (M, M-exp groups).
                     Dual-workspace layout: eval_ws/plan_ws/shared with symlinks
                     so neither agent can see the other's script.
      no_isolation — M-no-iso ablation. Single shared workspace — both agents
                     operate in the same directory and can see each other's
                     scripts (eval.py / action.py). ``shared/`` remains a real
                     subdir so path references are identical to the other modes.
                     Everything else (post-mortem, knowledge, trajectory) works
                     as in ``full`` mode. Use to measure the effect of isolation
                     on knowledge quality / co-evolution behavior.
      freeze_eval  — Evaluator runs only Round 1, frozen after (M-co-eval group)
      no_eval      — No independent Evaluator, Planner self-evaluates (M-no-eval group)
    """
    import sys

    # M-no-iso ablation: use a single shared workspace instead of dual-ws.
    # Path references (ws.eval_script, ws.metrics_json, ws.dataset, ...) still
    # resolve correctly because ``shared/`` is a real subdir under root.
    isolated = (mode != "no_isolation")
    ws = build_run_workspaces(prefix=f"forage_{spec.name}_", isolated=isolated)

    results_dir = Path(output_dir) / spec.name
    results_dir.mkdir(parents=True, exist_ok=True)

    # v2: tee stdout to forage.log for persistence
    log_path = results_dir / "forage.log"
    _log_tee = _LogTee(log_path)
    sys.stdout = _log_tee

    try:
        return _run_inner(spec, ws, results_dir, knowledge_dir, mode, log_path, enable_post_mortem)
    finally:
        sys.stdout = _log_tee.terminal
        _log_tee.close()


def _run_inner(spec, ws: RunWorkspaces, results_dir, knowledge_dir, mode, log_path, enable_post_mortem=True):
    """Inner run body — separated so stdout tee is always restored via try/finally."""
    from datetime import datetime, timezone

    history: list[RoundResult] = []
    total_cost_usd = 0.0
    metrics = {"coverage_estimate": 0.0, "total_collected": 0, "denominator": 0}
    eval_result_history: list[dict] = []
    planner_summaries: list[dict] = []

    # v2: create agents ONCE per run (explorer team mode)
    evaluator = EvaluatorAgent(
        private_ws=str(ws.eval_ws),
        shared_ws=str(ws.shared),
        knowledge_dir=knowledge_dir,
    )
    planner = PlannerAgent(
        private_ws=str(ws.plan_ws),
        shared_ws=str(ws.shared),
        knowledge_dir=knowledge_dir,
    )

    # Apply budget params from task spec
    evaluator.max_turns = spec.budget.max_turns_per_agent
    planner.max_turns = spec.budget.max_turns_per_agent
    evaluator.effort = spec.budget.effort
    planner.effort = spec.budget.effort
    evaluator.model = spec.budget.model
    planner.model = spec.budget.model

    # v2: stage knowledge files to the SHARED workspace so both agents see them
    if knowledge_dir:
        _stage_knowledge(knowledge_dir, ws.shared, spec)

    # v2: trajectory tracking
    trajectory = Trajectory(spec.name, {
        "name": spec.name,
        "description": spec.description,
        "topic": spec.topic,
        "coverage_target": spec.coverage.target,
    })
    trajectory.data["started_at"] = datetime.now(timezone.utc).isoformat()
    trajectory.data["run_config"] = {
        "mode": mode,
        "max_rounds": spec.budget.max_rounds,
        "max_turns_evaluator": evaluator.max_turns,
        "max_turns_planner": planner.max_turns,
        "effort": spec.budget.effort,
        "model": spec.budget.model,
        "agent_timeout_seconds": 1200,
        "max_requests": spec.budget.max_requests,
        "max_runtime_minutes": spec.budget.max_runtime_minutes,
    }

    print(f"  Run root: {ws.root}")
    if ws.eval_ws == ws.plan_ws == ws.root:
        print(f"    (non-isolated: single shared workspace — both agents use root)")
        print(f"    shared:   {ws.shared}")
    else:
        print(f"    eval_ws:  {ws.eval_ws}")
        print(f"    plan_ws:  {ws.plan_ws}")
        print(f"    shared:   {ws.shared}")

    print(f"\n{'#'*60}")
    print(f"# Forage v2: {spec.name}")
    print(f"# Topic: {spec.topic}")
    print(f"# Coverage target: {spec.coverage.target:.0%} ({spec.coverage.mode})")
    print(f"# Budget: {spec.budget.max_rounds} rounds | max_turns: {evaluator.max_turns} | effort: {spec.budget.effort} | model: {spec.budget.model} | Mode: {mode}")
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

        elif mode == "freeze_eval" and round_id > 1 and ws.eval_script.is_file():
            # M-co-eval: frozen after Round 1
            print("\n  [1/3] Evaluator: FROZEN (using round 1 eval.py)")
            metrics = run_eval_script(ws.eval_ws, ws.shared, "eval.py")
            if metrics.get("error"):
                print(f"         ERROR: eval.py failed: {metrics['error']}")
            coverage = _safe_coverage(metrics)
            print(f"         Coverage: {coverage:.1%}")
            # Hardcoded stop for frozen mode
            if coverage >= spec.coverage.target:
                should_stop = True
                print(f"         Decision: STOP (target reached)")

        else:
            # Full mode: run Evaluator (isolation is architectural — no hide/restore)
            label = "exploring data universe" if round_id == 1 else "auditing results"
            print(f"\n  [1/3] Evaluator: {label}...")

            eval_context = _build_evaluator_context(
                spec, history, ws, eval_result_history, planner_summaries,
            )
            eval_result = evaluator.run_with_recovery(eval_context, trajectory=trajectory)
            round_cost += evaluator.cost_usd
            _merge_usage(round_usage, evaluator.usage)

            # Unified fallback: if Evaluator response is bad, check workspace
            eval_ok = "denominator" in eval_result or "eval_script_path" in eval_result
            if not eval_ok:
                reason = eval_result.get("error", eval_result.get("text", "unknown")[:200])
                if ws.eval_script.is_file():
                    print(f"         WARNING: Evaluator response unusable ({reason[:100]}), but eval.py exists — proceeding")
                    salvaged = evaluator._salvage_from_workspace()
                    if salvaged:
                        eval_result = salvaged
                    else:
                        eval_result = {
                            "eval_script_path": "eval.py",
                            "denominator": "unknown",
                            "denominator_source": "unknown",
                            "denominator_confidence": "low",
                            "decision": "continue",
                            "decision_reason": "Salvaged eval.py from workspace",
                        }
                else:
                    print(f"         WARNING: Evaluator failed and no eval.py on disk — skipping round")
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

            # Read latest metrics from shared workspace (Evaluator may have run eval.py internally)
            metrics_path = ws.metrics_json
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
            records_total = _count_total_records(ws.shared)
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

        plan_context = _build_planner_context(
            spec, history, ws, eval_result_history, mode,
        )
        plan_result = planner.run_with_recovery(plan_context, trajectory=trajectory)
        round_cost += planner.cost_usd
        _merge_usage(round_usage, planner.usage)

        # Unified fallback: if Planner response is bad, check workspace
        plan_ok = "strategy_name" in plan_result or "action_script_path" in plan_result
        if not plan_ok:
            reason = plan_result.get("error", plan_result.get("text", "unknown")[:200])
            if ws.action_script.is_file():
                print(f"         WARNING: Planner response unusable ({str(reason)[:100]}), but action.py exists — proceeding")
                strategy = planner._salvage_from_workspace() or {"strategy_name": "salvaged", "action_script_path": "action.py"}
            elif any(ws.dataset.rglob("*")):
                # Math tasks: Planner may write directly to dataset/ without action.py
                print(f"         WARNING: No action.py but dataset/ has content — skipping Executor, running eval.py only")
                strategy = {"strategy_name": "direct_write", "action_script_path": None, "_skip_executor": True}
            else:
                print(f"         WARNING: Planner failed, no action.py, no dataset — skipping round")
                continue
        else:
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
        if strategy.get("_skip_executor"):
            print("\n  [3/3] Executor: SKIPPED (data written directly to dataset/)")
            exec_result = ExecutionResult(
                records_collected=0, requests_used=0, duration_seconds=0,
                stdout="", stderr="", exit_code=0,
            )
        else:
            print("\n  [3/3] Executor: running collection script...")
            action_script = strategy.get("action_script_path", "action.py")
            exec_result = execute_collection(
                plan_ws=ws.plan_ws,
                shared_ws=ws.shared,
                script_path=action_script,
                timeout=spec.budget.max_runtime_minutes * 60 // spec.budget.max_rounds,
            )
            print(f"         Collected: {exec_result.records_collected} records ({exec_result.duration_seconds:.0f}s)")

            if exec_result.error:
                print(f"         Error: {exec_result.error}")

        # --- Step 4: Run eval.py (deterministic, for next round's Evaluator) ---
        eval_script = "eval.py"
        if ws.eval_script.is_file():
            metrics = run_eval_script(ws.eval_ws, ws.shared, eval_script)
        coverage = _safe_coverage(metrics)
        print(f"         Coverage: {coverage:.1%}")

        # Record results
        duration = time.time() - t0
        total_cost_usd += round_cost
        records_total = _count_total_records(ws.shared)

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

        # v2: snapshot scripts per round (track strategy evolution)
        round_snapshots = results_dir / "round_snapshots" / f"r{round_id:02d}"
        round_snapshots.mkdir(parents=True, exist_ok=True)
        import shutil
        if ws.action_script.is_file():
            shutil.copy(ws.action_script, round_snapshots / "action.py")
        if ws.eval_script.is_file():
            shutil.copy(ws.eval_script, round_snapshots / "eval.py")

        # v2: record trajectory
        trajectory.add_round({
            "round_id": round_id,
            "duration_seconds": duration,
            "denominator": eval_result.get("denominator") or metrics.get("denominator", "unknown"),
            "denominator_source": eval_result.get("denominator_source") or metrics.get("denominator_source", "?"),
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

        denominator = metrics.get("denominator", "?")
        print(f"\n  >> Coverage: {coverage:.1%} ({denominator} denominator) | Records: {records_total} | Time: {duration:.0f}s")

        if should_stop:
            print(f"\n  STOPPING: Planner decided to stop")
            break

    # v2: save trajectory
    trajectory.data["ended_at"] = datetime.now(timezone.utc).isoformat()
    trajectory.set_final_state({
        "decision": history[-1].decision if history else "unknown",
        "final_coverage": _safe_coverage(metrics),
        "final_denominator": metrics.get("denominator", "unknown"),
        "final_records": _count_total_records(ws.shared),
    })
    # v2: post-mortem phase (only for M+ / M+-no-iso groups — M/M-exp don't accumulate)
    if mode in ("full", "no_isolation") and knowledge_dir and enable_post_mortem:
        pm_cost = _run_post_mortem(evaluator, planner, trajectory, knowledge_dir, ws, results_dir)
        total_cost_usd += pm_cost
        trajectory.data["total_cost_usd"] += pm_cost

    trajectory.save(results_dir / "trajectory.json")

    # --- Final: archive workspace artifacts to results_dir for debugging ---
    import shutil
    artifacts_dir = results_dir / "workspace"
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir)
    try:
        # symlinks=True keeps the shared-symlinks inside eval_ws/plan_ws intact.
        shutil.copytree(ws.root, artifacts_dir, symlinks=True)
    except (OSError, shutil.Error) as exc:
        # Archival is best-effort; a broken symlink shouldn't kill the run.
        print(f"  WARNING: workspace archival failed ({exc}); continuing")

    cleanup_workspaces(ws.root)

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

    def isatty(self):
        return False

    @property
    def encoding(self):
        return self.terminal.encoding

    def fileno(self):
        return self.terminal.fileno()


# --- Context builders ---


def _build_evaluator_context(
    spec: TaskSpec,
    history: list[RoundResult],
    ws: RunWorkspaces,
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

        # Self-audit checklist — every round, not just when coverage is met
        parts.append("\n🔍 Self-audit checklist (ask yourself EVERY round):")
        parts.append("  - Is my denominator still accurate? Could the real boundary be larger than I've defined?")
        parts.append("  - Is my eval.py rigorous enough? Would it catch subtle errors or edge cases?")
        parts.append("  - Am I being too lenient? Would a skeptical reviewer trust my evaluation?")
        parts.append("  - If outputs > denominator, should I expand the denominator instead of accepting >100% coverage?")

        # Previous metrics
        if history:
            last = history[-1]
            last_coverage = _safe_coverage(last.metrics)
            parts.append(f"\nPrevious round coverage: {last_coverage:.1%}")
            parts.append(f"Total records so far: {last.records_total}")

            # Saturation detection — soft hint to trigger explore mode
            # Three signals: fast target hit / denominator stable / over-collection
            saturation_reasons = []
            if last_coverage >= spec.coverage.target and round_id <= 3:
                saturation_reasons.append(
                    f"target hit in Round {round_id - 1} (suspiciously fast — may be incomplete)"
                )
            if eval_result_history and len(eval_result_history) >= 3:
                recent = [str(e.get("denominator")) for e in eval_result_history[-3:]]
                if len(set(recent)) == 1 and recent[0] != "None":
                    saturation_reasons.append(
                        f"denominator stable at {recent[-1]} for 3+ rounds (may be stuck in current frame)"
                    )
            last_denom = last.metrics.get("denominator")
            if isinstance(last_denom, (int, float)) and last_denom > 0:
                records_ratio = last.records_total / last_denom
                if records_ratio > 1.1:
                    saturation_reasons.append(
                        f"records ({last.records_total}) > denominator ({last_denom}) by {records_ratio:.0%} "
                        f"— denominator may be under-counted"
                    )

            if saturation_reasons:
                parts.append("\n🧭 Saturation signal — consider explore mode:")
                for reason in saturation_reasons:
                    parts.append(f"  - {reason}")
                parts.append("  Before stopping, explicitly audit completeness:")
                parts.append("    - Name adjacent directions (sources, approaches, dimensions) you have NOT checked")
                parts.append("    - Try at least one, or rule it out with specific reason")
                parts.append("    - Document unexplored directions as knowledge entries for future runs")

            if last.metrics.get("gaps"):
                parts.append(f"Gaps:\n{json.dumps(last.metrics['gaps'], indent=2)}")

        # Denominator history
        if eval_result_history:
            parts.append("\nDenominator history:")
            for e in eval_result_history:
                parts.append(f"  R{e['round']}: {e['denominator']} (source: {e.get('denominator_source', '?')}, confidence: {e.get('denominator_confidence', '?')})")

        # Previous eval.py content summary (lives in eval_ws, not shared)
        if ws and ws.eval_script.is_file():
            eval_content = ws.eval_script.read_text()
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
    parts.append("Write eval.py to your private workspace before responding.")

    return "\n".join(parts)


def _build_planner_context(
    spec: TaskSpec,
    history: list[RoundResult],
    ws: RunWorkspaces,
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

    # Include metrics from eval.py if available (lives in shared/)
    if ws and ws.metrics_json.is_file():
        try:
            m = json.loads(ws.metrics_json.read_text())
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

    parts.append("\nPropose a collection strategy and write action.py to your private workspace.")

    # Format reminder (prevents drift in persistent sessions)
    parts.append("\n## IMPORTANT: Output format")
    parts.append("Respond with a JSON object containing: strategy_name, strategy_description, target_source, expected_records, action_script_path.")

    return "\n".join(parts)


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


def _count_total_records(shared_ws: Path) -> int:
    """Count total records in shared_ws/dataset/ directory only."""
    dataset_dir = shared_ws / "dataset"
    if not dataset_dir.is_dir():
        return 0
    total = 0
    for f in dataset_dir.rglob("*.jsonl"):
        try:
            with open(f) as fh:
                total += sum(1 for _ in fh)
        except (OSError, UnicodeDecodeError):
            pass
    if total == 0:
        for f in dataset_dir.rglob("*.json"):
            total += 1
    return total


def _stage_knowledge(knowledge_dir: str, shared_ws: Path, spec: TaskSpec):
    """Copy ALL accumulated knowledge to the shared workspace (v2).

    Staged copy lives in ``shared_ws/knowledge`` so both Evaluator and Planner
    see the same knowledge through their ``./shared/knowledge/`` symlink path.
    After post-mortem, the staged copy is synced back to the persistent
    ``knowledge_dir``.

    All scopes are staged (universal, task_type, and any agent-created scopes like
    ``bioinformatics_api`` or ``data_collection_evaluation``). Earlier versions
    only staged universal + task_type, which silently discarded most accumulated
    knowledge and broke the Knowledge Evolution claim.
    """
    import shutil
    src = Path(knowledge_dir)
    dst = shared_ws / "knowledge"
    if not src.exists():
        dst.mkdir(exist_ok=True)
        return

    # Copy the entire knowledge tree — all scopes + INDEX.md.
    # dirs_exist_ok=True handles the case where dst was pre-populated (e.g. seeded).
    shutil.copytree(src, dst, dirs_exist_ok=True)


def _run_post_mortem(evaluator, planner, trajectory, knowledge_dir, ws: RunWorkspaces, results_dir):
    """Run post-mortem: each agent extracts lessons from the run (v2).

    Agents write lessons into their private/shared workspaces; we harvest the
    structured JSON response, persist ``write_knowledge_entry`` to the real
    ``knowledge_dir``, then sync the staged shared knowledge tree back so any
    raw .md files the agents dropped there make it to persistent storage.
    """
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

    # Extract and write lessons — permissive parsing to avoid silent drops.
    # Agents may return JSON in several shapes: [...], {"items": [...]},
    # {"lessons": [...]}, or even a single lesson dict. Drop nothing silently.
    all_lessons = []
    dropped_responses = []

    def _extract_lessons(result, source: str):
        """Pull out a list of lesson dicts from whatever shape the agent returned."""
        if result is None:
            return
        if isinstance(result, list):
            all_lessons.extend(result)
            return
        if isinstance(result, dict):
            # Look for any list-valued key that contains dict entries with 'id'
            for key in ("items", "lessons", "entries", "results"):
                val = result.get(key)
                if isinstance(val, list):
                    all_lessons.extend(val)
                    return
            # Single lesson dict with 'id' field
            if "id" in result and "scope" in result:
                all_lessons.append(result)
                return
            # Nothing recognizable — log raw response for audit
            dropped_responses.append((source, result))
        else:
            dropped_responses.append((source, result))

    _extract_lessons(eval_lessons, "evaluator")
    _extract_lessons(plan_lessons, "planner")

    # Save raw responses that couldn't be parsed, for audit
    if dropped_responses:
        import json as _json
        audit_dir = results_dir / "post_mortem_audit"
        audit_dir.mkdir(exist_ok=True)
        for source, raw in dropped_responses:
            audit_path = audit_dir / f"{source}_raw.json"
            try:
                audit_path.write_text(_json.dumps(raw, indent=2, default=str))
            except Exception:
                audit_path.write_text(str(raw))
            print(f"  Warning: post-mortem {source} response unrecognized — raw saved to {audit_path}")

    for lesson in all_lessons:
        if isinstance(lesson, dict) and "id" in lesson:
            write_knowledge_entry(knowledge_path, lesson)

    # Sync staged knowledge back to the persistent knowledge_dir — the agents
    # see ``./shared/knowledge/`` as their working copy, and any raw files they
    # wrote there need to land in the real knowledge_dir before next run.
    import shutil
    staged_knowledge = ws.knowledge  # ws.shared / "knowledge"
    if staged_knowledge.is_dir():
        shutil.copytree(staged_knowledge, knowledge_path, dirs_exist_ok=True)

    # Regenerate INDEX (covers both the structured writes above and any raw
    # .md files picked up by the sync).
    if all_lessons or staged_knowledge.is_dir():
        regenerate_index(knowledge_path)

    # Save knowledge snapshot
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
