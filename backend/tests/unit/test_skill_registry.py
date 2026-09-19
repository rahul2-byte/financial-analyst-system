from __future__ import annotations

from pathlib import Path

import pytest
from app.core.skills import SkillRegistry, SkillValidationError


def test_bundled_registry_loads_finance_skills() -> None:
    registry = SkillRegistry.bundled()

    assert set(registry.ids()) == {
        "equity-research",
        "technical-analysis",
        "fundamental-analysis",
        "news-evidence",
        "report-synthesis",
    }


def test_bundled_skills_reference_only_registered_tools() -> None:
    registry = SkillRegistry.bundled()
    registered = {
        "data:fetch_stock_data",
        "analysis:get_technical_overview",
        "data:fetch_fundamentals",
        "news:fetch_news",
        "analysis:run_fundamental_scan",
        "analysis:run_technical_scan",
        "interaction:ask_user",
    }

    for skill_id in registry.ids():
        unknown = set(registry.get(skill_id).manifest.allowed_tools) - registered
        assert not unknown, f"{skill_id} references unknown tools: {unknown}"


def test_registry_rejects_unknown_tools(tmp_path: Path) -> None:
    package = tmp_path / "bad-skill"
    package.mkdir()
    (package / "SKILL.md").write_text(
        "---\n"
        "id: bad-skill\n"
        "version: 1.0.0\n"
        "description: bad\n"
        "triggers: [bad]\n"
        "allowed_tools: [missing:tool]\n"
        "---\n\nUse the missing tool.\n",
        encoding="utf-8",
    )

    with pytest.raises(SkillValidationError, match="unknown tool"):
        SkillRegistry.load(
            tmp_path,
            registered_tools={"known:tool"},
        )


def test_registry_selects_deterministically() -> None:
    registry = SkillRegistry.bundled()

    selected = registry.select("Compare revenue, gross margin, and valuation")

    assert selected[0].manifest.id == "fundamental-analysis"
    assert selected == registry.select("Compare revenue, gross margin, and valuation")


@pytest.mark.parametrize(
    ("query", "skill_id"),
    [
        ("technical trend RSI", "technical-analysis"),
        ("fundamental valuation", "fundamental-analysis"),
        ("news sentiment", "news-evidence"),
        ("write a report", "report-synthesis"),
    ],
)
def test_registry_routes_supported_workflows(query: str, skill_id: str) -> None:
    selected = SkillRegistry.bundled().select(query)

    assert selected and selected[0].manifest.id == skill_id


def test_registry_normalizes_common_finance_query_aliases() -> None:
    registry = SkillRegistry.bundled()

    selected = registry.select("Analyse HDFC stock")

    assert selected
    assert selected[0].manifest.id == "equity-research"


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
