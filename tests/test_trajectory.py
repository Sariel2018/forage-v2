# tests/test_trajectory.py
import tempfile
from pathlib import Path
from forage.core.trajectory import Trajectory


def test_trajectory_save_load():
    t = Trajectory("test_task", {"name": "test"})
    t.add_round({"round_id": 1, "coverage": 0.5, "round_cost_usd": 1.0})
    t.set_final_state({"final_coverage": 0.5})

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "trajectory.json"
        t.save(path)

        loaded = Trajectory.load(path)
        assert len(loaded.data["rounds"]) == 1
        assert loaded.data["total_cost_usd"] == 1.0


def test_trajectory_render_narrative():
    t = Trajectory("test_task", {})
    t.add_round({
        "round_id": 1,
        "denominator": 100,
        "denominator_source": "sitemap",
        "denominator_confidence": "medium",
        "discovery": "Found 100 items",
        "strategy_name": "bulk_download",
        "target_source": "sitemap.xml",
        "strategy_description": "Download all",
        "records_collected": 50,
        "coverage": 0.5,
        "error_count": 0,
    })

    full = t.render_narrative("full")
    assert "denominator=100" in full
    assert "bulk_download" in full

    eval_view = t.render_narrative("evaluator")
    assert "denominator=100" in eval_view
    # Evaluator view should NOT contain planner-specific info (strategy_name)
    assert "bulk_download" not in eval_view


def test_trajectory_cost_accumulation():
    t = Trajectory("test_task", {})
    t.add_round({"round_id": 1, "round_cost_usd": 1.5})
    t.add_round({"round_id": 2, "round_cost_usd": 2.5})
    assert t.data["total_cost_usd"] == 4.0


def test_trajectory_render_planner_view():
    t = Trajectory("test_task", {})
    t.add_round({
        "round_id": 1,
        "denominator": 100,
        "denominator_source": "sitemap",
        "denominator_confidence": "medium",
        "discovery": "Found 100 items",
        "strategy_name": "bulk_download",
        "target_source": "sitemap.xml",
        "strategy_description": "Download all items via sitemap",
        "records_collected": 50,
        "coverage": 0.5,
        "error_count": 0,
    })

    planner_view = t.render_narrative("planner")
    assert "bulk_download" in planner_view
    assert "Download all items via sitemap" in planner_view
    # Planner view should NOT include evaluator-specific info
    assert "denominator=100" not in planner_view


def test_trajectory_render_with_errors():
    t = Trajectory("test_task", {})
    t.add_round({
        "round_id": 1,
        "denominator": 100,
        "denominator_source": "sitemap",
        "denominator_confidence": "medium",
        "discovery": "",
        "strategy_name": "bulk_download",
        "target_source": "sitemap.xml",
        "strategy_description": "",
        "records_collected": 50,
        "coverage": 0.5,
        "error_count": 3,
    })

    full = t.render_narrative("full")
    assert "Errors: 3" in full


def test_trajectory_save_creates_parent_dirs():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "nested" / "dir" / "trajectory.json"
        t = Trajectory("test_task", {})
        t.save(path)
        assert path.exists()


def test_trajectory_final_state():
    t = Trajectory("test_task", {})
    t.set_final_state({"decision": "stop", "final_coverage": 0.95})
    assert t.data["final_state"]["decision"] == "stop"
    assert t.data["final_state"]["final_coverage"] == 0.95
