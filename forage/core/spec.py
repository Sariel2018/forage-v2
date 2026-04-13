"""Task specification loader and validator."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class CoverageSpec:
    mode: str  # "hard" or "soft"
    target: float  # 0.0 - 1.0
    dimensions: list[str]  # e.g. ["time", "record", "type"]


@dataclass
class QualitySpec:
    min_text_length: int
    required_fields: list[str]
    dedup: bool = True


@dataclass
class BudgetSpec:
    max_rounds: int
    max_runtime_minutes: int
    max_requests: int
    max_turns_per_agent: int = 15


@dataclass
class RiskSpec:
    respect_robots_txt: bool = True
    max_requests_per_minute: int = 15
    forbidden_sources: list[str] = field(default_factory=list)


@dataclass
class SourcesSpec:
    seed_sources: list[str] = field(default_factory=list)
    preferred_sources: list[str] = field(default_factory=list)
    forbidden_sources: list[str] = field(default_factory=list)


@dataclass
class TaskSpec:
    """Complete task specification for a Forage run."""

    name: str
    description: str
    topic: str
    time_range: dict[str, str]  # {"start": "...", "end": "..."}
    doc_type: str
    language: str
    coverage: CoverageSpec
    quality: QualitySpec
    budget: BudgetSpec
    risk: RiskSpec
    sources: SourcesSpec
    task_type: str = "web_scraping"

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TaskSpec":
        """Load a task spec from a YAML file."""
        with open(path) as f:
            raw = yaml.safe_load(f)

        task = raw["task"]
        target = raw["target"]

        return cls(
            name=task["name"],
            description=task["description"],
            topic=target["topic"],
            time_range=target["time_range"],
            doc_type=target["doc_type"],
            language=target["language"],
            coverage=CoverageSpec(**raw["coverage"]),
            quality=QualitySpec(**raw["quality"]),
            budget=BudgetSpec(**raw["budget"]),
            risk=RiskSpec(**raw["risk"]),
            sources=SourcesSpec(**raw["sources"]),
            task_type=task.get("task_type", "web_scraping"),
        )
