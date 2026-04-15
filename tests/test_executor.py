import json
import tempfile
from pathlib import Path
from forage.agents.executor import execute_collection


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
