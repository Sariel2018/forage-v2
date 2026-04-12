# forage/core/trajectory.py
"""Trajectory data persistence — saves per-round structured data."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class TrajectoryRound:
    """One round's data in the trajectory."""
    round_id: int
    duration_seconds: float
    denominator: int | str
    denominator_source: str
    denominator_confidence: str
    discovery: str
    evaluator_decision: str
    strategy_name: str
    target_source: str
    strategy_description: str
    records_collected: int
    records_total: int
    coverage: float
    error_count: int
    exit_code: int
    knowledge_files_read: dict  # {"evaluator": [...], "planner": [...]}
    round_cost_usd: float


class Trajectory:
    """Manages trajectory.json for a single run."""

    def __init__(self, task_id: str, task_spec: dict):
        self.data = {
            "task_id": task_id,
            "task_spec": task_spec,
            "started_at": None,
            "ended_at": None,
            "total_cost_usd": 0.0,
            "rounds": [],
            "final_state": {},
        }

    def add_round(self, round_data: dict):
        """Add a round's data."""
        self.data["rounds"].append(round_data)
        self.data["total_cost_usd"] += round_data.get("round_cost_usd", 0)

    def set_final_state(self, state: dict):
        """Set the final state after the run completes."""
        self.data["final_state"] = state

    def save(self, path: Path):
        """Save trajectory to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=2, default=str, ensure_ascii=False))

    @classmethod
    def load(cls, path: Path) -> "Trajectory":
        """Load trajectory from JSON file."""
        data = json.loads(path.read_text())
        t = cls(data["task_id"], data.get("task_spec", {}))
        t.data = data
        return t

    def render_narrative(self, view: str = "full") -> str:
        """Render trajectory as narrative text for agent consumption.

        view: "full" | "evaluator" | "planner"
        """
        lines = []
        for r in self.data["rounds"]:
            rid = r.get("round_id", "?")
            lines.append(f"## Round {rid}")

            if view in ("full", "evaluator"):
                lines.append(
                    f"Evaluator: denominator={r.get('denominator', '?')} "
                    f"(source: {r.get('denominator_source', '?')}, "
                    f"confidence: {r.get('denominator_confidence', '?')})"
                )
                if r.get("discovery"):
                    lines.append(f"Discovery: {r['discovery']}")

            if view in ("full", "planner"):
                lines.append(
                    f"Strategy: {r.get('strategy_name', '?')} → {r.get('target_source', '?')}"
                )
                if r.get("strategy_description"):
                    lines.append(f"  Description: {r['strategy_description']}")

            lines.append(
                f"Result: {r.get('records_collected', 0)} records, "
                f"coverage {r.get('coverage', 0):.1%}"
            )
            if r.get("error_count", 0) > 0:
                lines.append(f"  Errors: {r['error_count']}")
            lines.append("")

        return "\n".join(lines)
