#!/usr/bin/env python3
"""Export per-round evolution data for all Whitehouse experiment runs to CSV."""

import csv
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent / "experiments_whitehouse" / "whitehouse_trump2"
TASK_NAME = "whitehouse_trump2"
MAX_ROUNDS = 8  # harness max rounds

GROUPS_HARNESS = ["M", "M-co-eval", "M-exp", "M-no-eval", "M-no-iso"]
GROUPS_ALL = GROUPS_HARNESS + ["SA"]

EVOLUTION_COLS = [
    "group", "run", "round_id", "round_effective",
    "denominator", "denominator_source", "denominator_changed",
    "coverage_estimate", "records_total", "records_collected_this_round",
    "strategy_name", "target_source", "strategy_description",
    "decision", "cost_usd", "round_duration_seconds", "agent_failures",
]

SUMMARY_COLS = [
    "group", "run",
    "total_effective_rounds", "total_rounds_attempted",
    "wasted_rounds",
    "final_denominator", "denominator_evolution_path",
    "final_coverage", "final_records",
    "total_cost_usd", "total_duration_seconds",
    "stop_reason",
]


def load_history(run_dir: Path) -> list[dict]:
    """Load history.jsonl from a harness run."""
    hist_path = run_dir / TASK_NAME / "history.jsonl"
    if not hist_path.exists():
        return []
    entries = []
    with open(hist_path) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def load_run_result(run_dir: Path) -> dict:
    rr_path = run_dir / "run_result.json"
    if not rr_path.exists():
        return {}
    with open(rr_path) as f:
        return json.load(f)


def extract_round_row(entry: dict, prev_records_total: int, prev_denominator) -> dict:
    """Extract a CSV row from a history entry."""
    metrics = entry.get("metrics", {})
    strategy = entry.get("strategy", {})

    denominator = metrics.get("denominator", "")
    denominator_source = metrics.get("denominator_source", "")
    coverage = metrics.get("coverage_estimate", "")
    records_total = entry.get("records_total", 0)
    records_this_round = entry.get("records_collected", 0)

    denom_changed = ""
    if prev_denominator is not None and denominator != "":
        denom_changed = str(denominator != prev_denominator).lower()

    # Detect failures from gaps/notes
    failures = []
    gaps = metrics.get("gaps", {})
    if isinstance(gaps, dict):
        for k, v in gaps.items():
            if any(kw in str(v).lower() for kw in ["ssl", "error", "timeout", "fail", "interrupt"]):
                failures.append(f"{k}: {v}")
    elif isinstance(gaps, list):
        for g in gaps:
            if any(kw in str(g).lower() for kw in ["ssl", "error", "timeout", "fail", "interrupt"]):
                failures.append(str(g))

    notes = strategy.get("notes", "")
    if any(kw in notes.lower() for kw in ["ssl error", "timeout", "fail"]):
        failures.append(f"strategy_notes: {notes[:200]}")

    if records_this_round == 0 and records_total == prev_records_total:
        failures.append("zero_new_records")

    return {
        "round_id": f"R{entry['round_id']}",
        "round_effective": "true",
        "denominator": denominator,
        "denominator_source": denominator_source,
        "denominator_changed": denom_changed,
        "coverage_estimate": coverage,
        "records_total": records_total,
        "records_collected_this_round": records_this_round,
        "strategy_name": strategy.get("strategy_name", ""),
        "target_source": strategy.get("target_source", ""),
        "strategy_description": strategy.get("strategy_description", ""),
        "decision": entry.get("decision", ""),
        "cost_usd": entry.get("cost_usd", ""),
        "round_duration_seconds": entry.get("duration_seconds", ""),
        "agent_failures": "; ".join(failures) if failures else "",
    }


def process_harness_run(group: str, run_name: str, run_dir: Path):
    """Process a harness run, returning (detail_rows, summary_row)."""
    history = load_history(run_dir)
    run_result = load_run_result(run_dir)

    if not history and not run_result:
        return [], None

    # Build round map
    round_map = {e["round_id"]: e for e in history}
    recorded_rounds = set(round_map.keys())

    detail_rows = []
    prev_records = 0
    prev_denom = None
    denominators = []

    for rid in range(1, MAX_ROUNDS + 1):
        if rid in round_map:
            entry = round_map[rid]
            row = extract_round_row(entry, prev_records, prev_denom)
            row["group"] = group
            row["run"] = run_name

            denom = entry.get("metrics", {}).get("denominator", "")
            if denom != "" and (not denominators or denominators[-1] != denom):
                denominators.append(denom)
            prev_denom = denom
            prev_records = entry.get("records_total", prev_records)

            detail_rows.append(row)
        else:
            # Skipped/failed round
            detail_rows.append({
                "group": group,
                "run": run_name,
                "round_id": f"R{rid}",
                "round_effective": "false",
                "denominator": "",
                "denominator_source": "",
                "denominator_changed": "",
                "coverage_estimate": "",
                "records_total": "",
                "records_collected_this_round": "",
                "strategy_name": "",
                "target_source": "",
                "strategy_description": "",
                "decision": "",
                "cost_usd": "",
                "round_duration_seconds": "",
                "agent_failures": "round_skipped_or_failed",
            })

    # Summary row
    effective_rounds = len(recorded_rounds)
    max_round = max(recorded_rounds) if recorded_rounds else 0
    wasted = max_round - effective_rounds if max_round > 0 else 0

    # Get final values from last recorded round
    last_entry = history[-1] if history else {}
    final_metrics = last_entry.get("metrics", {})

    summary = {
        "group": group,
        "run": run_name,
        "total_effective_rounds": effective_rounds,
        "total_rounds_attempted": max_round,
        "wasted_rounds": wasted,
        "final_denominator": final_metrics.get("denominator", run_result.get("final_coverage", "")),
        "denominator_evolution_path": "->".join(str(d) for d in denominators),
        "final_coverage": run_result.get("final_coverage", final_metrics.get("coverage_estimate", "")),
        "final_records": run_result.get("total_records", last_entry.get("records_total", "")),
        "total_cost_usd": run_result.get("total_cost_usd", ""),
        "total_duration_seconds": run_result.get("duration_seconds", ""),
        "stop_reason": run_result.get("stop_reason", ""),
    }

    return detail_rows, summary


def process_sa_run(run_name: str, run_dir: Path):
    """Process a SA run (single agent, no rounds)."""
    run_result = load_run_result(run_dir)
    if not run_result:
        return [], None

    detail_row = {
        "group": "SA",
        "run": run_name,
        "round_id": "R1",
        "round_effective": "true",
        "denominator": "",
        "denominator_source": "",
        "denominator_changed": "",
        "coverage_estimate": str(run_result.get("final_coverage", ""))[:100],
        "records_total": run_result.get("total_records", ""),
        "records_collected_this_round": run_result.get("total_records", ""),
        "strategy_name": "single_agent_free_form",
        "target_source": "",
        "strategy_description": str(run_result.get("stop_reason", ""))[:300],
        "decision": "stop",
        "cost_usd": run_result.get("total_cost_usd", ""),
        "round_duration_seconds": run_result.get("duration_seconds", ""),
        "agent_failures": "",
    }

    summary = {
        "group": "SA",
        "run": run_name,
        "total_effective_rounds": 1,
        "total_rounds_attempted": 1,
        "wasted_rounds": 0,
        "final_denominator": "unknown",
        "denominator_evolution_path": "unknown",
        "final_coverage": run_result.get("final_coverage", ""),
        "final_records": run_result.get("total_records", ""),
        "total_cost_usd": run_result.get("total_cost_usd", ""),
        "total_duration_seconds": run_result.get("duration_seconds", ""),
        "stop_reason": str(run_result.get("stop_reason", ""))[:200],
    }

    return [detail_row], summary


def main():
    all_detail = []
    all_summary = []

    for group in GROUPS_ALL:
        group_dir = BASE_DIR / group
        if not group_dir.exists():
            print(f"WARNING: {group_dir} not found, skipping")
            continue

        run_dirs = sorted([d for d in group_dir.iterdir() if d.is_dir() and d.name.startswith("run_")])

        for run_dir in run_dirs:
            run_name = run_dir.name
            print(f"Processing {group}/{run_name}...")

            if group == "SA":
                details, summary = process_sa_run(run_name, run_dir)
            else:
                details, summary = process_harness_run(group, run_name, run_dir)

            all_detail.extend(details)
            if summary:
                all_summary.append(summary)

    # Write evolution CSV
    evo_path = BASE_DIR / "whitehouse_evolution.csv"
    with open(evo_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EVOLUTION_COLS)
        writer.writeheader()
        writer.writerows(all_detail)
    print(f"\nWrote {len(all_detail)} rows to {evo_path}")

    # Write summary CSV
    sum_path = BASE_DIR / "whitehouse_run_summary.csv"
    with open(sum_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_COLS)
        writer.writeheader()
        writer.writerows(all_summary)
    print(f"Wrote {len(all_summary)} rows to {sum_path}")


if __name__ == "__main__":
    main()
