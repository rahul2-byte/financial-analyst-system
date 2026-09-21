from pathlib import Path

import pytest
from app.core.prompts import (
    PromptConfigurationError,
    PromptNotFoundError,
    PromptRegistry,
    PromptRenderError,
)


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_get_and_render_prompt(tmp_path: Path) -> None:
    registry = PromptRegistry.load(
        _write(
            tmp_path / "prompts.yaml",
            "prompts:\n  agent:\n    system:\n      template: |\n        Hello {name}\n        {name}\n",
        )
    )

    assert registry.get("agent.system") == "Hello {name}\n{name}\n"
    assert registry.render("agent.system", name="Rahul") == "Hello Rahul\nRahul\n"


def test_missing_prompt_and_variables_fail(tmp_path: Path) -> None:
    registry = PromptRegistry.load(
        _write(
            tmp_path / "prompts.yaml",
            "prompts:\n  agent:\n    system:\n      template: Hello {name}\n",
        )
    )

    with pytest.raises(PromptNotFoundError):
        registry.get("agent.missing")
    with pytest.raises(PromptRenderError, match="missing variable"):
        registry.render("agent.system")
    with pytest.raises(PromptRenderError, match="unexpected variable"):
        registry.render("agent.system", name="x", extra="y")


@pytest.mark.parametrize(
    "yaml_text",
    [
        "",
        "other: {}\n",
        "prompts: []\n",
        "prompts:\n  agent:\n    system:\n      template: null\n",
        "prompts:\n  agent:\n    system:\n      template: [bad]\n",
        "prompts:\n  agent:\n    system:\n      template: '{bad.name}'\n",
    ],
)
def test_invalid_prompt_configuration_fails(tmp_path: Path, yaml_text: str) -> None:
    with pytest.raises(PromptConfigurationError):
        PromptRegistry.load(_write(tmp_path / "prompts.yaml", yaml_text))


def test_duplicate_yaml_key_fails(tmp_path: Path) -> None:
    with pytest.raises(PromptConfigurationError, match="duplicate"):
        PromptRegistry.load(
            _write(
                tmp_path / "prompts.yaml",
                "prompts:\n  agent:\n    system:\n      template: one\n    system:\n      template: two\n",
            )
        )


def test_bundled_prompts_keep_runtime_contracts() -> None:
    registry = PromptRegistry.bundled()

    required = {
        "agent_loop.core.system",
        "agent_loop.report.system",
        "agent_loop.report.availability",
        "agent_loop.report.evidence_failure_availability",
        "agent_loop.retry.empty_answer",
        "agent_loop.retry.empty_report",
        "agent_loop.retry.output_review",
        "agent_loop.tool.duplicate_request",
        "agent_loop.tool.untrusted_content",
        "agent_loop.tool.evidence_failure",
        "agent_loop.tool.invalid_arguments",
        "agent_loop.clarification.ticker",
        "publication.report_repair",
        "session.resolved_instrument",
        "session.compacted_history",
        "session.research_plan",
        "session.normalized_scope",
        "jev.route.instructions",
        "jev.review.instructions",
        "tools.interaction_ask_user.description",
        "skills.report_synthesis",
    }
    assert required <= set(registry.keys())
    assert "[[fact:" in registry.get("agent_loop.report.system")
    assert "untrusted data" in registry.get("agent_loop.tool.untrusted_content")
    assert "source" in registry.get("agent_loop.tool.evidence_failure").lower()
    clarification = registry.get("agent_loop.clarification.ticker")
    assert "AAPL" not in clarification
    assert "HDFCBANK.NS" in clarification
    assert registry.render("session.research_plan", focal_ticker="NSE:TCS", peer_universe="NSE:INFY", default_timeframe="1y")
