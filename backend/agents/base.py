import asyncio
import uuid
from typing import Optional, Any
from backend.app.models.response_models import StreamEvent, ToolStatus


class BaseAgent:
    """
    Base class for all agents in the system.
    Provides methods for LLM interaction and status reporting.
    """

    def __init__(self, llm_service: Any, model: str):
        self.llm_service = llm_service
        self.model = model
        self.status_queue: Optional[asyncio.Queue] = None
        self.agent_name = self.__class__.__name__

    async def emit_status(
        self,
        step_number: int,
        tool_name: str,
        input_desc: str,
        output_desc: Optional[str] = None,
        status: str = "running",
        tool_id: Optional[str] = None,
    ) -> str:
        """
        Emits a status event to the status queue if it exists.
        """
        if not tool_id:
            tool_id = str(uuid.uuid4())

        if self.status_queue:
            tool_status = ToolStatus(
                tool_id=tool_id,
                step_number=step_number,
                agent=self.agent_name,
                tool_name=tool_name,
                status=status,
                input=input_desc,
                output=output_desc,
            )
            await self.status_queue.put(
                StreamEvent(event="tool_status", data=tool_status)
            )

        return tool_id
