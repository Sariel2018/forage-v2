"""Integration smoke test for Forage v2 dual-workspace isolation.

Goes beyond the purely structural checks in ``test_isolation_regression.py``:
this test actually exercises ``forage.core.loop.run()`` end-to-end with the
Claude CLI mocked out, and then performs a CLI-log audit to verify that each
agent's transcripts do not mention the OTHER agent's private script file
(``action.py`` must not leak into evaluator logs, and ``eval.py`` must not
leak into planner logs).

Mocking strategy
----------------

We patch ``forage.agents.base.subprocess.run``. Because both ``base`` and
``executor`` import the same ``subprocess`` module object, this attribute
patch rebinds ``subprocess.run`` globally — so the fake must dispatch: if
the command starts with ``"claude"`` it returns a canned stream-json
response, otherwise it delegates to the real ``subprocess.run`` so the
Executor can actually invoke python on the staged ``action.py`` / ``eval.py``
scripts. This gives us a true end-to-end flow: mocked agents "write"
scripts to their private workspaces, and the harness really executes them
against the shared directory — exactly the path real runs take.

Because the mocked Claude CLI responses are deterministic, we pin
``max_rounds=1`` so the loop makes exactly one Evaluator + Planner call
before terminating.
"""

from __future__ import annotations

import json
import subprocess as _real_subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

# Capture the real subprocess.run reference BEFORE any patching can shadow it.
# The mock dispatcher delegates non-claude calls (executor running python on
# eval.py / action.py) to this real function.
_REAL_RUN = _real_subprocess.run

from forage.core.spec import (
    BudgetSpec,
    CoverageSpec,
    QualitySpec,
    RiskSpec,
    SourcesSpec,
    TaskSpec,
)
from forage.core.loop import run


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _minimal_spec() -> TaskSpec:
    """Build a TaskSpec small enough to run one loop round quickly."""
    return TaskSpec(
        name="smoke_test",
        description="integration smoke test",
        topic="test_topic",
        time_range={"start": "", "end": ""},
        doc_type="test",
        language="en",
        coverage=CoverageSpec(mode="soft", target=0.9, dimensions=[]),
        quality=QualitySpec(min_text_length=0, required_fields=[]),
        budget=BudgetSpec(
            max_rounds=1,
            max_runtime_minutes=5,
            max_requests=10,
            max_turns_per_agent=3,
            effort="medium",
            model="opus",
        ),
        risk=RiskSpec(respect_robots_txt=True, max_requests_per_minute=30),
        sources=SourcesSpec(),
        task_type="api",
    )


# --- Canned stream-json responses --------------------------------------------

_EVAL_RESULT_JSON = {
    "eval_script_path": "eval.py",
    "denominator": 10,
    "denominator_source": "mock-sitemap",
    "denominator_confidence": "high",
    "denominator_changed": False,
    "denominator_history": "R1: 10",
    "discovery": "mock discovery — 10 items observed",
    "new_sources_found": [],
    "decision": "continue",
    "decision_reason": "Round 1 initial exploration",
}

_PLAN_RESULT_JSON = {
    "strategy_name": "mock_strategy",
    "strategy_description": "write five fake records to the dataset",
    "target_source": "mock://source",
    "expected_records": 5,
    "action_script_path": "action.py",
    "notes": "",
}


def _stream_json_line(result_payload: dict, cost_usd: float = 0.01) -> str:
    """Render a single stream-json line containing a type=result frame.

    The harness's parser (``_parse_claude_output``) walks the lines looking for
    ``{"type": "result", ...}`` and extracts cost from the same frame.
    """
    return json.dumps({
        "type": "result",
        "subtype": "success",
        "result": json.dumps(result_payload),
        "total_cost_usd": cost_usd,
        "usage": {"input_tokens": 100, "output_tokens": 50},
    })


# --- Mock side-effects -------------------------------------------------------


_EVAL_PY_BODY = '''\
"""Fake eval.py written by mocked Evaluator.

Counts JSONL lines in ./shared/dataset/ and writes ./shared/metrics.json.
This script is intentionally self-contained: the harness runs it with
cwd=eval_ws and ``shared`` resolves via the symlink.
"""
import json
from pathlib import Path

shared = Path("shared")
dataset = shared / "dataset"

total = 0
if dataset.is_dir():
    for f in dataset.rglob("*.jsonl"):
        with open(f) as fh:
            total += sum(1 for _ in fh)

denominator = 10
metrics = {
    "coverage_estimate": min(1.0, total / denominator) if denominator else 0.0,
    "total_collected": total,
    "denominator": denominator,
    "denominator_source": "mock-sitemap",
}
(shared / "metrics.json").write_text(json.dumps(metrics))
'''


_ACTION_PY_BODY = '''\
"""Fake action.py written by mocked Planner.

Writes five JSON records to ./shared/dataset/data.jsonl and emits a
FORAGE_RESULT line so the Executor parses record counts cleanly.
"""
import json
import os

os.makedirs("shared/dataset", exist_ok=True)
with open("shared/dataset/data.jsonl", "w") as f:
    for i in range(5):
        f.write(json.dumps({"id": i, "value": f"item-{i}"}) + "\\n")

print('FORAGE_RESULT:{"records": 5, "requests": 5}')
'''


_EVAL_CONTRACT_BODY = """\
# Evaluation contract (mock)

## Expected output from Planner
- Write JSONL records to `./shared/dataset/*.jsonl`
- Each record must contain `id` and `value` fields

## What eval.py measures
- coverage_estimate = collected / denominator (denominator=10)
"""


def _write_evaluator_artifacts(cwd: Path) -> None:
    """Write the artifacts a real Evaluator would produce into its workspace."""
    (cwd / "eval.py").write_text(_EVAL_PY_BODY)
    # eval_contract.md lives in shared/ (written via the ./shared symlink)
    contract = cwd / "shared" / "eval_contract.md"
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text(_EVAL_CONTRACT_BODY)


def _write_planner_artifacts(cwd: Path) -> None:
    """Write the artifacts a real Planner would produce into its workspace."""
    (cwd / "action.py").write_text(_ACTION_PY_BODY)


def _build_completed_process(stdout: str, returncode: int = 0) -> MagicMock:
    """Build a subprocess.CompletedProcess-shaped MagicMock."""
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = ""
    return result


def _mock_claude_run_factory():
    """Build a subprocess.run replacement that simulates claude CLI calls only.

    - Intercepts commands whose first arg is ``"claude"``.
    - Dispatches based on cwd (eval_ws vs plan_ws) to decide which agent is
      calling, then writes the role-appropriate artifacts to disk and returns
      a canned stream-json response.
    """

    def _mock_run(cmd, **kwargs):  # noqa: ANN001 — mirrors subprocess.run signature
        is_claude = isinstance(cmd, (list, tuple)) and len(cmd) > 0 and cmd[0] == "claude"
        if not is_claude:
            # Executor running python on eval.py/action.py; delegate to real
            # subprocess so the staged scripts actually execute.
            return _REAL_RUN(cmd, **kwargs)

        cwd = Path(kwargs.get("cwd", "."))
        cwd_str = str(cwd)
        if "eval_ws" in cwd_str:
            _write_evaluator_artifacts(cwd)
            return _build_completed_process(_stream_json_line(_EVAL_RESULT_JSON))
        elif "plan_ws" in cwd_str:
            _write_planner_artifacts(cwd)
            return _build_completed_process(_stream_json_line(_PLAN_RESULT_JSON))
        else:
            raise RuntimeError(f"Unexpected cwd for mocked claude call: {cwd}")

    return _mock_run


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_full_loop_smoke(tmp_path):
    """Drive run() end-to-end with mocked Claude CLI; verify artifacts + audit.

    Checks:
    1. run() completes without exception and returns >= 1 RoundResult.
    2. Archived workspace (``results/smoke_test/workspace/``) contains
       eval_ws/eval.py and plan_ws/action.py in their respective private
       directories — confirming dual-workspace layout persists after run.
    3. shared/ contains metrics.json, eval_contract.md, and dataset/data.jsonl
       (the "public contract surface" was actually exercised).
    4. CLI-log audit: Planner's stdout logs don't mention ``eval.py`` and the
       Evaluator's don't mention ``action.py`` — the specific regression we
       are guarding against. Only the canned stream-json payloads ever land
       in CLI logs under this mock, so any leak would be a real bug.
    """
    spec = _minimal_spec()
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    mock_run = _mock_claude_run_factory()

    # Patch ONLY the subprocess.run used by the agent base class. The executor
    # continues to call the real subprocess.run to actually invoke python on
    # the staged eval.py / action.py scripts.
    with patch("forage.agents.base.subprocess.run", side_effect=mock_run):
        history = run(
            spec=spec,
            output_dir=str(output_dir),
            knowledge_dir=None,
            mode="full",
            enable_post_mortem=False,  # no post-mortem without knowledge_dir anyway
        )

    # --- 1. Loop completed and recorded at least one round --------------------
    assert len(history) >= 1, f"Expected at least one RoundResult, got {history!r}"
    first = history[0]
    assert first.round_id == 1
    # The fake action.py wrote 5 records; eval.py should have tallied them.
    assert first.records_total == 5, f"Expected 5 records, got {first.records_total}"

    # --- 2. Archived workspace structure --------------------------------------
    results_dir = output_dir / "smoke_test"
    artifacts = results_dir / "workspace"
    assert artifacts.is_dir(), (
        f"Expected archived workspace at {artifacts}; results_dir contents: "
        f"{list(results_dir.iterdir())}"
    )

    eval_ws_archived = artifacts / "eval_ws"
    plan_ws_archived = artifacts / "plan_ws"
    shared_archived = artifacts / "shared"

    assert (eval_ws_archived / "eval.py").is_file(), "eval.py missing from eval_ws"
    assert (plan_ws_archived / "action.py").is_file(), "action.py missing from plan_ws"

    # Cross-workspace leakage check: agent scripts must NOT be physically
    # duplicated into the other agent's private dir.
    assert not (eval_ws_archived / "action.py").exists(), \
        "action.py must not exist in eval_ws (isolation violation)"
    assert not (plan_ws_archived / "eval.py").exists(), \
        "eval.py must not exist in plan_ws (isolation violation)"

    # --- 3. Shared contract surface -------------------------------------------
    assert (shared_archived / "metrics.json").is_file()
    assert (shared_archived / "eval_contract.md").is_file()
    assert (shared_archived / "dataset").is_dir()
    jsonl_files = list((shared_archived / "dataset").glob("*.jsonl"))
    assert jsonl_files, "No JSONL records in shared/dataset after run"

    metrics = json.loads((shared_archived / "metrics.json").read_text())
    assert metrics["total_collected"] == 5
    assert metrics["denominator"] == 10

    # --- 4. CLI-log audit: the regression guard -------------------------------
    eval_log_dir = eval_ws_archived / "cli_logs"
    plan_log_dir = plan_ws_archived / "cli_logs"
    assert eval_log_dir.is_dir(), f"Evaluator cli_logs missing at {eval_log_dir}"
    assert plan_log_dir.is_dir(), f"Planner cli_logs missing at {plan_log_dir}"

    eval_stdouts = sorted(eval_log_dir.glob("*_stdout.json"))
    plan_stdouts = sorted(plan_log_dir.glob("*_stdout.json"))
    assert eval_stdouts, "No Evaluator stdout logs captured"
    assert plan_stdouts, "No Planner stdout logs captured"

    # These checks catch the exact regression documented in
    # tests/test_isolation_regression.py's header: a Planner transcript that
    # mentions `eval.py` means the agent saw the other team's private script.
    for log in plan_stdouts:
        content = log.read_text()
        assert "eval.py" not in content, (
            f"LEAK: 'eval.py' mentioned in Planner CLI log {log}. "
            f"First 500 chars: {content[:500]!r}"
        )
    for log in eval_stdouts:
        content = log.read_text()
        assert "action.py" not in content, (
            f"LEAK: 'action.py' mentioned in Evaluator CLI log {log}. "
            f"First 500 chars: {content[:500]!r}"
        )


def test_cli_log_audit_detects_planted_leak(tmp_path):
    """Meta-test: the audit pattern must actually flag a planted leak.

    Without this test, the primary smoke test could silently pass even if the
    grep-style assertion was structurally broken (e.g. reading from the wrong
    path). We manually build the post-run workspace layout and plant a leak,
    then assert the same pattern the main test uses would catch it.
    """
    from forage.core.workspace import build_run_workspaces, cleanup_workspaces

    ws = build_run_workspaces(prefix="audit_meta_")
    try:
        # Write normal private artifacts
        (ws.eval_ws / "eval.py").write_text(_EVAL_PY_BODY)
        (ws.plan_ws / "action.py").write_text(_ACTION_PY_BODY)

        # Set up cli_logs like base.py would
        eval_logs = ws.eval_ws / "cli_logs"
        plan_logs = ws.plan_ws / "cli_logs"
        eval_logs.mkdir()
        plan_logs.mkdir()

        # Plant a leak: Planner's log mentions eval.py (the forbidden word)
        leaked = plan_logs / "r01_planner_stdout.json"
        leaked.write_text('{"type":"assistant","message":"let me read eval.py"}')

        # A clean Evaluator log for comparison
        (eval_logs / "r01_evaluator_stdout.json").write_text(
            '{"type":"result","result":"denominator=10"}'
        )

        # Run the same audit the integration test uses
        def scan(log_dir: Path, forbidden: str) -> list[Path]:
            hits = []
            for log in log_dir.glob("*_stdout.json"):
                if forbidden in log.read_text():
                    hits.append(log)
            return hits

        planner_leaks = scan(plan_logs, "eval.py")
        evaluator_leaks = scan(eval_logs, "action.py")

        assert planner_leaks == [leaked], (
            f"Audit failed to detect planted Planner leak; got {planner_leaks}"
        )
        assert evaluator_leaks == [], (
            f"Unexpected Evaluator leak detection: {evaluator_leaks}"
        )
    finally:
        cleanup_workspaces(ws.root)
