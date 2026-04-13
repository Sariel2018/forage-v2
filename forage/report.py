"""Generate simple HTML report from trajectory.json using Plotly."""

import json
from pathlib import Path


def generate_report(trajectory_path: Path, output_path: Path | None = None):
    """Generate a single-file HTML report from trajectory.json."""
    data = json.loads(trajectory_path.read_text())

    rounds = data.get("rounds", [])
    if not rounds:
        print("No rounds in trajectory")
        return

    # Extract time series
    round_ids = [r["round_id"] for r in rounds]
    coverages = [r.get("coverage", 0) for r in rounds]
    denominators = [r.get("denominator", 0) for r in rounds]
    costs = [r.get("round_cost_usd", 0) for r in rounds]

    final_state = data.get("final_state", {})
    final_coverage = final_state.get("final_coverage", coverages[-1] if coverages else 0)
    total_cost = data.get("total_cost_usd", sum(costs))

    # Build round cards HTML
    round_cards = ""
    for r in rounds:
        coverage_val = r.get("coverage", 0)
        try:
            coverage_str = f"{float(coverage_val):.1%}"
        except (ValueError, TypeError):
            coverage_str = str(coverage_val)

        round_cards += f"""
    <div class="round-card">
        <h3>Round {r.get('round_id', '?')} (${r.get('round_cost_usd', 0):.2f})</h3>
        <p><strong>Evaluator:</strong> denominator={r.get('denominator', '?')} ({r.get('denominator_source', '?')})</p>
        <p><strong>Discovery:</strong> {r.get('discovery', 'none')}</p>
        <p><strong>Strategy:</strong> {r.get('strategy_name', '?')} &mdash; {r.get('strategy_description', '')}</p>
        <p><strong>Result:</strong> {r.get('records_collected', 0)} records, coverage {coverage_str}, errors: {r.get('error_count', 0)}</p>
    </div>
"""

    # Handle non-numeric denominators
    numeric_denoms = []
    for d in denominators:
        try:
            numeric_denoms.append(float(d))
        except (ValueError, TypeError):
            numeric_denoms.append(0)

    coverage_pcts = []
    for c in coverages:
        try:
            coverage_pcts.append(float(c) * 100)
        except (ValueError, TypeError):
            coverage_pcts.append(0)

    task_id = data.get("task_id", "unknown")

    try:
        final_coverage_str = f"{float(final_coverage):.1%}"
    except (ValueError, TypeError):
        final_coverage_str = str(final_coverage)

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Forage Run Report &mdash; {task_id}</title>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <style>
        body {{
            font-family: Georgia, serif;
            background: #faf8f5;
            color: #333;
            max-width: 900px;
            margin: 0 auto;
            padding: 20px;
        }}
        h1 {{ color: #4a6741; }}
        h2 {{ color: #6b8f63; border-bottom: 1px solid #d4c5a9; padding-bottom: 8px; }}
        .metrics {{ margin: 16px 0; }}
        .metric {{
            display: inline-block;
            margin: 10px 20px 10px 0;
            padding: 10px 20px;
            background: #eee8dc;
            border-radius: 8px;
        }}
        .metric .value {{ font-size: 24px; font-weight: bold; color: #4a6741; }}
        .metric .label {{ font-size: 12px; color: #888; }}
        .chart {{ margin: 20px 0; }}
        .round-card {{
            background: white;
            border: 1px solid #d4c5a9;
            border-radius: 8px;
            padding: 16px;
            margin: 12px 0;
        }}
        .round-card h3 {{ color: #4a6741; margin-top: 0; }}
    </style>
</head>
<body>
    <h1>Forage Run Report</h1>
    <p><strong>Task:</strong> {task_id}</p>

    <div class="metrics">
        <div class="metric"><div class="value">{final_coverage_str}</div><div class="label">Final Coverage</div></div>
        <div class="metric"><div class="value">${total_cost:.2f}</div><div class="label">Total Cost</div></div>
        <div class="metric"><div class="value">{len(rounds)}</div><div class="label">Rounds</div></div>
    </div>

    <h2>Coverage Progress</h2>
    <div id="coverage-chart" class="chart"></div>

    <h2>Denominator Evolution</h2>
    <div id="denominator-chart" class="chart"></div>

    <h2>Round-by-Round Timeline</h2>
{round_cards}
    <script>
    Plotly.newPlot('coverage-chart', [{{
        x: {json.dumps(round_ids)},
        y: {json.dumps(coverage_pcts)},
        mode: 'lines+markers',
        marker: {{color: '#4a6741'}},
        line: {{color: '#4a6741', width: 2}},
        name: 'Coverage %'
    }}], {{
        yaxis: {{title: 'Coverage %'}},
        xaxis: {{title: 'Round', dtick: 1}},
        margin: {{t: 20}},
        paper_bgcolor: '#faf8f5',
        plot_bgcolor: '#faf8f5'
    }});

    Plotly.newPlot('denominator-chart', [{{
        x: {json.dumps(round_ids)},
        y: {json.dumps(numeric_denoms)},
        mode: 'lines+markers',
        marker: {{color: '#b8860b'}},
        line: {{color: '#b8860b', width: 2}},
        name: 'Denominator'
    }}], {{
        yaxis: {{title: 'Denominator'}},
        xaxis: {{title: 'Round', dtick: 1}},
        margin: {{t: 20}},
        paper_bgcolor: '#faf8f5',
        plot_bgcolor: '#faf8f5'
    }});
    </script>
</body>
</html>"""

    if output_path is None:
        output_path = trajectory_path.parent / "report.html"
    output_path.write_text(html)
    print(f"Report generated: {output_path}")
