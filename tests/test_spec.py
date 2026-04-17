# tests/test_spec.py
import pytest
from pathlib import Path
from forage.core.spec import BudgetSpec, TaskSpec


def test_budget_spec_model_default():
    """BudgetSpec defaults model to 'opus'."""
    budget = BudgetSpec(max_rounds=8, max_runtime_minutes=180, max_requests=5000)
    assert budget.model == "opus"


def test_budget_spec_model_custom():
    """BudgetSpec accepts custom model."""
    budget = BudgetSpec(max_rounds=8, max_runtime_minutes=180, max_requests=5000, model="sonnet")
    assert budget.model == "sonnet"


def test_budget_spec_effort_valid():
    """BudgetSpec accepts low/medium/high/max."""
    for level in ["low", "medium", "high", "max"]:
        b = BudgetSpec(max_rounds=8, max_runtime_minutes=180, max_requests=5000, effort=level)
        assert b.effort == level


def test_budget_spec_effort_invalid():
    """BudgetSpec rejects unknown effort levels."""
    with pytest.raises(ValueError, match="Unknown effort"):
        BudgetSpec(max_rounds=8, max_runtime_minutes=180, max_requests=5000, effort="extreme")


def test_from_yaml_loads_model(tmp_path):
    """TaskSpec.from_yaml loads model field from YAML."""
    yaml_content = """\
task:
  name: "test_task"
  description: "test"
  task_type: "web_scraping"
target:
  topic: "test"
  time_range: {start: "", end: ""}
  doc_type: "test"
  language: "en"
coverage:
  target: 0.90
  mode: "soft"
  dimensions: []
quality:
  min_text_length: 0
  required_fields: []
budget:
  max_rounds: 8
  max_requests: 1000
  max_runtime_minutes: 60
  model: "sonnet"
risk:
  respect_robots_txt: true
  max_requests_per_minute: 30
sources:
  seed_sources: []
  preferred_sources: []
"""
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content)
    spec = TaskSpec.from_yaml(spec_path)
    assert spec.budget.model == "sonnet"


def test_from_yaml_defaults_model(tmp_path):
    """TaskSpec.from_yaml defaults model to 'opus' when not specified."""
    yaml_content = """\
task:
  name: "test_task"
  description: "test"
target:
  topic: "test"
  time_range: {start: "", end: ""}
  doc_type: "test"
  language: "en"
coverage:
  target: 0.90
  mode: "soft"
  dimensions: []
quality:
  min_text_length: 0
  required_fields: []
budget:
  max_rounds: 8
  max_requests: 1000
  max_runtime_minutes: 60
risk:
  respect_robots_txt: true
  max_requests_per_minute: 30
sources:
  seed_sources: []
  preferred_sources: []
"""
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content)
    spec = TaskSpec.from_yaml(spec_path)
    assert spec.budget.model == "opus"


def test_budget_spec_rejects_typo():
    """BudgetSpec rejects unknown model names."""
    with pytest.raises(ValueError, match="Unknown model 'sonet'"):
        BudgetSpec(max_rounds=8, max_runtime_minutes=180, max_requests=5000, model="sonet")


def test_budget_spec_accepts_full_model_id():
    """BudgetSpec accepts full Claude model IDs."""
    budget = BudgetSpec(max_rounds=8, max_runtime_minutes=180, max_requests=5000, model="claude-sonnet-4-6")
    assert budget.model == "claude-sonnet-4-6"


def test_nvidia_sonnet_cold_spec_loads():
    """nvidia_gpu_sonnet_cold.yaml loads with pinned model."""
    spec_path = Path(__file__).parent.parent / "tasks" / "nvidia_gpu_sonnet_cold.yaml"
    assert spec_path.exists(), "Expected task spec file missing"
    spec = TaskSpec.from_yaml(spec_path)
    assert spec.budget.model == "claude-sonnet-4-6"


def test_nvidia_sonnet_seeded_spec_loads():
    """nvidia_gpu_sonnet_seeded.yaml loads with pinned model."""
    spec_path = Path(__file__).parent.parent / "tasks" / "nvidia_gpu_sonnet_seeded.yaml"
    assert spec_path.exists(), "Expected task spec file missing"
    spec = TaskSpec.from_yaml(spec_path)
    assert spec.budget.model == "claude-sonnet-4-6"
