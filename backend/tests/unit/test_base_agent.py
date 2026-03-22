import asyncio
import uuid
import pytest
from agents.base import BaseAgent
from app.models.response_models import ToolStatus, StreamEvent


from app.services.llm_interface import LLMServiceInterface


class MockLLMService(LLMServiceInterface):
    def generate_stream(self, *args, **kwargs):
        pass

    async def generate(self, *args, **kwargs):
        pass

    async def generate_message(self, *args, **kwargs):
        pass

    async def check_health(self):
        return True


def test_tool_status_model():
    """Test ToolStatus Pydantic model."""
    status_data = {
        "tool_id": "test-uuid",
        "step_number": 1,
        "agent": "research_agent",
        "tool_name": "web_search",
        "status": "running",
        "input": "test query",
        "output": None,
    }
    tool_status = ToolStatus(**status_data)
    assert tool_status.tool_id == "test-uuid"
    assert tool_status.status == "running"


def test_stream_event_with_tool_status():
    """Test StreamEvent with ToolStatus payload."""
    status_data = {
        "tool_id": "test-uuid",
        "step_number": 1,
        "agent": "research_agent",
        "tool_name": "web_search",
        "status": "completed",
        "input": "test query",
        "output": "search results",
    }
    tool_status = ToolStatus(**status_data)

    event = StreamEvent(event="tool_status", data=tool_status)
    assert event.event == "tool_status"
    assert isinstance(event.data, ToolStatus)
    assert event.data.output == "search results"


@pytest.mark.asyncio
async def test_base_agent_init():
    llm = MockLLMService()
    agent = BaseAgent(llm_service=llm, model="gpt-4")
    assert agent.llm_service == llm
    assert agent.model == "gpt-4"
    assert agent.status_queue is None


@pytest.mark.asyncio
async def test_base_agent_emit_status():
    llm = MockLLMService()
    queue = asyncio.Queue()
    agent = BaseAgent(llm_service=llm, model="gpt-4")
    agent.status_queue = queue

    # Test emitting status
    tool_id = await agent.emit_status(
        step_number=1, tool_name="test_tool", input_desc="test input", status="running"
    )

    assert tool_id is not None
    assert isinstance(uuid.UUID(tool_id), uuid.UUID)

    # Verify queue message
    event = await queue.get()
    assert event.event == "tool_status"
    assert isinstance(event.data, ToolStatus)
    assert event.data.tool_id == tool_id
    assert event.data.status == "running"
    assert event.data.tool_name == "test_tool"


@pytest.mark.asyncio
async def test_base_agent_emit_status_with_provided_id():
    llm = MockLLMService()
    queue = asyncio.Queue()
    agent = BaseAgent(llm_service=llm, model="gpt-4")
    agent.status_queue = queue

    specific_id = str(uuid.uuid4())
    tool_id = await agent.emit_status(
        step_number=2,
        tool_name="other_tool",
        input_desc="input",
        status="completed",
        output_desc="output",
        tool_id=specific_id,
    )

    assert tool_id == specific_id

    event = await queue.get()
    assert event.data.tool_id == specific_id
    assert event.data.output == "output"
    assert event.data.status == "completed"
