"""Tests for v2 loop architecture."""
import inspect
import json
from pathlib import Path
from forage.core.loop import run, _build_evaluator_context, _build_planner_context
from forage.core.workspace import build_run_workspaces, cleanup_workspaces


def test_run_signature_v2():
    """run() should accept mode parameter."""
    sig = inspect.signature(run)
    assert "mode" in sig.parameters


def test_evaluator_context_round1():
    """Round 1 context should indicate initial exploration."""
    from forage.core.spec import TaskSpec, CoverageSpec, QualitySpec, BudgetSpec, RiskSpec, SourcesSpec
    spec = TaskSpec(
        name="test", description="test task", topic="test topic",
        time_range={"start": "2020-01-01", "end": "2020-12-31"},
        doc_type="article", language="en",
        coverage=CoverageSpec(mode="soft", target=0.9, dimensions=["time"]),
        quality=QualitySpec(min_text_length=100, required_fields=["title"]),
        budget=BudgetSpec(max_rounds=5, max_runtime_minutes=60, max_requests=1000),
        risk=RiskSpec(), sources=SourcesSpec(),
    )
    ctx = _build_evaluator_context(spec, history=[], ws=None, eval_result_history=[], planner_summaries=[])
    assert "Round: 1" in ctx
    assert "Round 1" in ctx


def test_evaluator_context_round2_has_denominator_history():
    """Round 2+ context should include denominator history and strategy summary."""
    from forage.core.spec import TaskSpec, CoverageSpec, QualitySpec, BudgetSpec, RiskSpec, SourcesSpec
    from forage.core.loop import RoundResult
    spec = TaskSpec(
        name="test", description="test task", topic="test topic",
        time_range={"start": "2020-01-01", "end": "2020-12-31"},
        doc_type="article", language="en",
        coverage=CoverageSpec(mode="soft", target=0.9, dimensions=["time"]),
        quality=QualitySpec(min_text_length=100, required_fields=["title"]),
        budget=BudgetSpec(max_rounds=5, max_runtime_minutes=60, max_requests=1000),
        risk=RiskSpec(), sources=SourcesSpec(),
    )
    history = [RoundResult(
        round_id=1, strategy={"strategy_name": "sitemap_crawl", "target_source": "https://example.com/sitemap.xml"},
        records_collected=0, records_total=100, metrics={"coverage_estimate": 0.5, "denominator": 200},
        eval_script_version="eval.py", duration_seconds=60, decision="continue", cost_usd=1.0, usage={},
    )]
    eval_history = [{"round": 1, "denominator": 200, "denominator_source": "sitemap", "denominator_confidence": "medium"}]
    planner_summaries = [{"round": 1, "strategy_name": "sitemap_crawl", "target_source": "https://example.com/sitemap.xml"}]

    ctx = _build_evaluator_context(spec, history, ws=None, eval_result_history=eval_history, planner_summaries=planner_summaries)
    assert "sitemap_crawl" in ctx
    assert "200" in ctx
    assert "Round: 2" in ctx


def test_planner_context_has_discovery():
    """Planner context should include Evaluator's discovery."""
    from forage.core.spec import TaskSpec, CoverageSpec, QualitySpec, BudgetSpec, RiskSpec, SourcesSpec
    spec = TaskSpec(
        name="test", description="test task", topic="test topic",
        time_range={"start": "2020-01-01", "end": "2020-12-31"},
        doc_type="article", language="en",
        coverage=CoverageSpec(mode="soft", target=0.9, dimensions=["time"]),
        quality=QualitySpec(min_text_length=100, required_fields=["title"]),
        budget=BudgetSpec(max_rounds=5, max_runtime_minutes=60, max_requests=1000),
        risk=RiskSpec(), sources=SourcesSpec(),
    )
    eval_history = [{"round": 1, "denominator": 1650, "denominator_source": "CDX", "denominator_confidence": "high",
                     "discovery": "CDX wildcard reveals 1650 articles", "new_sources_found": ["https://web.archive.org/cdx"]}]

    ws = build_run_workspaces(prefix="test_planner_ctx_")
    try:
        ctx = _build_planner_context(spec, history=[], ws=ws, eval_result_history=eval_history, mode="full")
        assert "CDX wildcard" in ctx
        assert "1650" in ctx
    finally:
        cleanup_workspaces(ws.root)
