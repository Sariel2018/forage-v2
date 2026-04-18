import json
import tempfile
from pathlib import Path
from forage.agents.executor import execute_collection, run_eval_script


def _make_dual_workspace(root: Path) -> tuple[Path, Path]:
    """Create the dual-workspace layout and return (plan_ws, shared_ws)."""
    plan_ws = root / "plan_ws"
    shared_ws = root / "shared"
    plan_ws.mkdir()
    shared_ws.mkdir()
    (shared_ws / "dataset").mkdir()
    # Symlink so scripts running with cwd=plan_ws can reach ./shared/dataset/
    (plan_ws / "shared").symlink_to("../shared", target_is_directory=True)
    return plan_ws, shared_ws


def test_record_count_nested_dataset():
    """Executor should count JSONL records in nested dataset directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_ws, shared_ws = _make_dual_workspace(Path(tmpdir))

        # action.py writes into a nested subdir under shared/dataset/
        script = (
            "import os, json\n"
            "os.makedirs('shared/dataset/subdir', exist_ok=True)\n"
            "with open('shared/dataset/subdir/data.jsonl', 'w') as f:\n"
            "    for i in range(5):\n"
            "        f.write(json.dumps({'id': i}) + '\\n')\n"
            "print('done')\n"
        )
        (plan_ws / "action.py").write_text(script)

        result = execute_collection(
            plan_ws=plan_ws,
            shared_ws=shared_ws,
            script_path="action.py",
            timeout=30,
        )
        assert result.records_collected == 5, (
            f"Expected 5, got {result.records_collected}; stderr={result.stderr}"
        )


def test_record_count_direct_dataset():
    """Executor should count JSONL in direct dataset/ path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_ws, shared_ws = _make_dual_workspace(Path(tmpdir))

        script = (
            "import os, json\n"
            "os.makedirs('shared/dataset', exist_ok=True)\n"
            "with open('shared/dataset/data.jsonl', 'w') as f:\n"
            "    for i in range(3):\n"
            "        f.write(json.dumps({'id': i}) + '\\n')\n"
            "print('done')\n"
        )
        (plan_ws / "action.py").write_text(script)

        result = execute_collection(
            plan_ws=plan_ws,
            shared_ws=shared_ws,
            script_path="action.py",
            timeout=30,
        )
        assert result.records_collected == 3, (
            f"Expected 3, got {result.records_collected}; stderr={result.stderr}"
        )


def test_forage_result_line_takes_priority():
    """If action.py prints FORAGE_RESULT, use that count instead of file counting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_ws, shared_ws = _make_dual_workspace(Path(tmpdir))

        script = (
            'import json\n'
            'print("FORAGE_RESULT:" + json.dumps({"records": 42, "requests": 10}))\n'
        )
        (plan_ws / "action.py").write_text(script)

        result = execute_collection(
            plan_ws=plan_ws,
            shared_ws=shared_ws,
            script_path="action.py",
            timeout=30,
        )
        assert result.records_collected == 42
        assert result.requests_used == 10


# --- run_eval_script tests ---

def _make_eval_workspace(root: Path) -> tuple[Path, Path]:
    """Create eval workspace layout and return (eval_ws, shared_ws)."""
    eval_ws = root / "eval_ws"
    shared_ws = root / "shared"
    eval_ws.mkdir()
    shared_ws.mkdir()
    (shared_ws / "dataset").mkdir()
    (eval_ws / "shared").symlink_to("../shared", target_is_directory=True)
    return eval_ws, shared_ws


def test_run_eval_script_success():
    """run_eval_script returns metrics from eval.py output."""
    with tempfile.TemporaryDirectory() as tmpdir:
        eval_ws, shared_ws = _make_eval_workspace(Path(tmpdir))
        script = (
            "import json\n"
            "metrics = {'coverage_estimate': 0.85, 'denominator': 100}\n"
            "with open('shared/metrics.json', 'w') as f:\n"
            "    json.dump(metrics, f)\n"
        )
        (eval_ws / "eval.py").write_text(script)
        result = run_eval_script(eval_ws, shared_ws)
        assert result["coverage_estimate"] == 0.85
        assert result["denominator"] == 100


def test_run_eval_script_not_found():
    """run_eval_script returns error when eval.py doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        eval_ws, shared_ws = _make_eval_workspace(Path(tmpdir))
        result = run_eval_script(eval_ws, shared_ws)
        assert "error" in result
        assert "not found" in result["error"]


def test_run_eval_script_timeout():
    """run_eval_script catches timeout, writes error to metrics.json, doesn't crash."""
    with tempfile.TemporaryDirectory() as tmpdir:
        eval_ws, shared_ws = _make_eval_workspace(Path(tmpdir))
        script = "import time; time.sleep(10)\n"
        (eval_ws / "eval.py").write_text(script)
        result = run_eval_script(eval_ws, shared_ws, timeout=2)
        assert "error" in result
        assert "timed out" in result["error"]
        # Verify error was written to metrics.json
        metrics_path = shared_ws / "metrics.json"
        assert metrics_path.is_file()
        written = json.loads(metrics_path.read_text())
        assert "timed out" in written["error"]


def test_budget_spec_eval_timeout_default():
    """BudgetSpec defaults eval_timeout to 120."""
    from forage.core.spec import BudgetSpec
    budget = BudgetSpec(max_rounds=8, max_runtime_minutes=180, max_requests=5000)
    assert budget.eval_timeout == 120


def test_budget_spec_eval_timeout_custom():
    """BudgetSpec accepts custom eval_timeout."""
    from forage.core.spec import BudgetSpec
    budget = BudgetSpec(max_rounds=8, max_runtime_minutes=180, max_requests=5000, eval_timeout=600)
    assert budget.eval_timeout == 600
