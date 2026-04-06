import tempfile
from pathlib import Path
from forage.experiments.runner import _write_comparison


def test_comparison_handles_unknown_coverage():
    """Comparison table should handle string coverage values from SA."""
    results = {
        "SA": [
            {
                "group": "SA",
                "run": 1,
                "rounds": 1,
                "final_coverage": "unknown",
                "total_records": 3793,
                "total_cost_usd": 21.09,
                "duration_seconds": 1384,
                "stop_reason": "unknown",
            }
        ],
        "M": [
            {
                "group": "M",
                "run": 1,
                "rounds": 8,
                "final_coverage": 0.504,
                "total_records": 849,
                "total_cost_usd": 9.11,
                "duration_seconds": 7795,
                "stop_reason": "budget_exhausted",
            }
        ],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        exp_dir = Path(tmpdir)
        _write_comparison(results, exp_dir)
        md = (exp_dir / "comparison.md").read_text()
        assert "SA" in md
        assert "unknown" in md
        assert "50.4%" in md
