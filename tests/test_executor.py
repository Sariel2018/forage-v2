import json
import tempfile
from pathlib import Path
from forage.agents.executor import execute_collection


def test_record_count_nested_dataset():
    """Executor should count JSONL records in nested dataset directories."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)

        # Write a trivial collect.py that does nothing (no FORAGE_RESULT line)
        (ws / "collect.py").write_text("print('done')\n")

        # Place JSONL in a nested path (simulating agent behavior)
        nested = ws / "workspace" / "dataset"
        nested.mkdir(parents=True)
        with open(nested / "data.jsonl", "w") as f:
            for i in range(5):
                f.write(json.dumps({"id": i}) + "\n")

        result = execute_collection(workspace=ws, script_path="collect.py", timeout=30)
        assert result.records_collected == 5, f"Expected 5, got {result.records_collected}"


def test_record_count_direct_dataset():
    """Executor should count JSONL in direct dataset/ path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        (ws / "collect.py").write_text("print('done')\n")
        dataset = ws / "dataset"
        dataset.mkdir()
        with open(dataset / "data.jsonl", "w") as f:
            for i in range(3):
                f.write(json.dumps({"id": i}) + "\n")

        result = execute_collection(workspace=ws, script_path="collect.py", timeout=30)
        assert result.records_collected == 3, f"Expected 3, got {result.records_collected}"


def test_forage_result_line_takes_priority():
    """If collect.py prints FORAGE_RESULT, use that count instead of file counting."""
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        script = 'import json\nprint("FORAGE_RESULT:" + json.dumps({"records": 42, "requests": 10}))\n'
        (ws / "collect.py").write_text(script)

        result = execute_collection(workspace=ws, script_path="collect.py", timeout=30)
        assert result.records_collected == 42
        assert result.requests_used == 10
