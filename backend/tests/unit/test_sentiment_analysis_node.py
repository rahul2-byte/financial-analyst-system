from app.core.prompts import prompt_manager
from app.core.tools.tool_system import tool_registry


def test_sentiment_prompt_and_runtime_use_registered_tool_names_only():
    prompt = prompt_manager.get_prompt("sentiment.system")
    assert "run_finbert_analysis" not in prompt
    available_tool_names = {tool.name for tool in tool_registry.list_tools()}
    assert "submit_sentiment" in available_tool_names
