import pytest
from app.core.prompts import PromptManager


def test_prompt_manager_loads_and_formats():
    manager = PromptManager()
    # Mocking prompts to test without actual file content
    manager.prompts = {
        "technical": {"system": "You are a test agent.", "user": "Query: {query}"}
    }

    assert manager.get_prompt("technical.system") == "You are a test agent."
    assert manager.get_prompt("technical.user", query="Hello") == "Query: Hello"

    with pytest.raises(KeyError):
        manager.get_prompt("nonexistent.key")


def test_prompt_manager_loads_prompt_directory():
    manager = PromptManager()
    manager._load_prompts()

    assert "technical" in manager.prompts
    assert "autonomous_orchestrator" in manager.prompts
    assert isinstance(manager.get_prompt("technical.system"), str)
    assert isinstance(
        manager.get_prompt("autonomous_orchestrator.autonomous.critic"), str
    )


def test_prompt_manager_loads_interactive_planner_prompts():
    manager = PromptManager()
    manager._load_prompts()

    system_prompt = manager.get_prompt(
        "autonomous_orchestrator.interactive_planner.system"
    )
    user_prompt = manager.get_prompt(
        "autonomous_orchestrator.interactive_planner.user", query="test"
    )

    assert isinstance(system_prompt, str)
    assert isinstance(user_prompt, str)
    assert "response_mode" in system_prompt
    assert "ask_clarification" in system_prompt
    assert "ask_plan_approval" in system_prompt
    assert "direct_execution" in system_prompt
    assert "is_fast_track" in system_prompt


def test_prompt_manager_loads_centralized_node_prompts_and_ticker_resolver():
    manager = PromptManager()
    manager._load_prompts()

    ticker_resolver = manager.get_prompt(
        "autonomous_orchestrator.ticker_resolver.system"
    )
    sentiment_node = manager.get_prompt("sentiment.user_node", text="test text")
    macro_node = manager.get_prompt("macro.user_node", ticker="AAPL", data="{}")
    contrarian_node = manager.get_prompt(
        "contrarian.user_node",
        ticker="AAPL",
        data="{}",
    )

    assert "RELIANCE" in ticker_resolver
    assert "ambiguity_reason" in ticker_resolver
    assert "test text" in sentiment_node
    assert "AAPL" in macro_node
    assert "AAPL" in contrarian_node
