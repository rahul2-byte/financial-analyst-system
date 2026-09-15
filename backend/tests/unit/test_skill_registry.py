from __future__ import annotations

from pathlib import Path

import pytest
from app.core.skills import SkillRegistry, SkillValidationError


def test_bundled_registry_loads_finance_skills() -> None:
    registry = SkillRegistry.bundled()

    assert {
        "fundamental-analysis",
        "technical-analysis",
        "sentiment-analysis",
        "macro-analysis",
        "contrarian-analysis",
        "research-planning",
        "source-research",
        "report-writing",
        "thesis-review",
        "conflict-review",
        "report-review",
    } <= set(registry.ids())


def test_registry_selects_deterministically() -> None:
    registry = SkillRegistry.bundled()

    selected = registry.select("Compare revenue, gross margin, and valuation")

    assert selected[0].manifest.id == "fundamental-analysis"
    assert selected == registry.select("Compare revenue, gross margin, and valuation")


def test_registry_normalizes_common_finance_query_aliases() -> None:
    registry = SkillRegistry.bundled()

    selected = registry.select("Analyse HDFC stock")

    assert selected
    assert selected[0].manifest.id == "research-planning"


def test_registry_rejects_skill_paths_outside_package(tmp_path: Path) -> None:
    package = tmp_path / "bad-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\n"
        "id: bad-skill\n"
        "version: 1.0.0\n"
        "description: bad\n"
        "triggers: [bad]\n"
        "allowed_tools: []\n"
        "scripts: [../escape.py]\n"
        "references: []\n"
        "---\n\nDo not load this.\n",
        encoding="utf-8",
    )

    with pytest.raises(SkillValidationError, match="inside the skill package"):
        SkillRegistry.load(tmp_path)


def test_skill_prompt_is_bounded_and_contains_contract() -> None:
    skill = SkillRegistry.bundled().get("fundamental-analysis")

    prompt = skill.prompt()

    assert "fundamental-analysis" in prompt
    assert "verified" in prompt.lower()
    assert len(prompt) < 12_000
