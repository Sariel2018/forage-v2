"""Tests for forage.report — HTML report generation from trajectory.json."""

import json
import tempfile
from pathlib import Path

from forage.report import generate_report


def test_generate_report():
    """Report generates valid HTML from trajectory data."""
    trajectory = {
        "task_id": "test_task",
        "total_cost_usd": 2.50,
        "rounds": [
            {
                "round_id": 1,
                "coverage": 0.5,
                "denominator": 100,
                "denominator_source": "sitemap",
                "discovery": "Found sitemap",
                "strategy_name": "bulk",
                "strategy_description": "Download all",
                "records_collected": 50,
                "round_cost_usd": 1.25,
                "error_count": 0,
            },
            {
                "round_id": 2,
                "coverage": 0.9,
                "denominator": 100,
                "denominator_source": "sitemap",
                "discovery": "",
                "strategy_name": "fill_gaps",
                "strategy_description": "Fill missing",
                "records_collected": 40,
                "round_cost_usd": 1.25,
                "error_count": 1,
            },
        ],
        "final_state": {"final_coverage": 0.9},
    }

    with tempfile.TemporaryDirectory() as d:
        traj_path = Path(d) / "trajectory.json"
        traj_path.write_text(json.dumps(trajectory))

        generate_report(traj_path)

        report_path = Path(d) / "report.html"
        assert report_path.exists()
        html = report_path.read_text()
        assert "test_task" in html
        assert "90.0%" in html
        assert "plotly" in html.lower()
        assert "bulk" in html


def test_generate_report_custom_output():
    """Report can be written to a custom output path."""
    trajectory = {
        "task_id": "custom_output",
        "total_cost_usd": 1.00,
        "rounds": [
            {
                "round_id": 1,
                "coverage": 0.3,
                "denominator": 50,
                "records_collected": 15,
                "round_cost_usd": 1.00,
            },
        ],
        "final_state": {"final_coverage": 0.3},
    }

    with tempfile.TemporaryDirectory() as d:
        traj_path = Path(d) / "trajectory.json"
        traj_path.write_text(json.dumps(trajectory))

        out_path = Path(d) / "custom_report.html"
        generate_report(traj_path, out_path)

        assert out_path.exists()
        html = out_path.read_text()
        assert "custom_output" in html
        assert "$1.00" in html


def test_generate_report_empty_rounds(capsys):
    """Report handles empty rounds gracefully."""
    trajectory = {"task_id": "empty", "rounds": []}

    with tempfile.TemporaryDirectory() as d:
        traj_path = Path(d) / "trajectory.json"
        traj_path.write_text(json.dumps(trajectory))

        generate_report(traj_path)

        report_path = Path(d) / "report.html"
        assert not report_path.exists()

        captured = capsys.readouterr()
        assert "No rounds" in captured.out
