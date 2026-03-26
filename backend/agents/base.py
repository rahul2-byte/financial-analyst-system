import asyncio
import uuid
import contextvars
from typing import Optional, Any, Literal
from app.models.response_models import StreamEvent, ToolStatus
from app.services.llm_interface import LLMServiceInterface

# ContextVar to store the status queue for the current task/request
status_queue_var: contextvars.ContextVar[Optional[asyncio.Queue]] = (
    contextvars.ContextVar("status_queue", default=None)
)


class BaseAgent:
    """
    Base class for all agents in the system.

    This class provides core functionality for LLM interaction, configuration,
    and status reporting via an asynchronous queue. It serves as the parent
    for specialized agents (e.g., Search, Analysis, Retrieval).

    Attributes:
        llm_service (LLMServiceInterface): The service used to interact with LLMs.
        model (str): The specific model ID to use for generations.
        agent_name (str): The name of the agent, derived from the class name.
    """

    def __init__(self, llm_service: LLMServiceInterface, model: str):
        """
        Initializes the base agent.

        Args:
            llm_service (LLMServiceInterface): Implementation of LLM service.
            model (str): Name of the LLM model to use.
        """
        self.llm_service = llm_service
        self.model = model
        self.agent_name = self.__class__.__name__

    @property
    def status_queue(self) -> Optional[asyncio.Queue]:
        """Returns the status queue for the current context."""
        return status_queue_var.get()

    async def execute(self, user_query: str, step_number: int = 0) -> Any:
        """
        Executes the agent's core logic. To be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement execute()")

    async def emit_status(
        self,
        step_number: int,
        tool_name: str,
        input_desc: str,
        output_desc: Optional[str] = None,
        status: Literal["running", "completed", "error"] = "running",
        tool_id: Optional[str] = None,
    ) -> str:
        """
        Emits a status event to the status queue if it exists.

        This method is used by subclasses to provide real-time feedback
        to the frontend about the progress of tool execution.

        Args:
            step_number (int): The current execution step within a plan.
            tool_name (str): Name of the tool or action being performed.
            input_desc (str): Brief description of the input given to the tool.
            output_desc (Optional[str]): Result or summary of the tool execution.
            status (str): Current status ("running", "completed", "error").
            tool_id (Optional[str]): Persistent ID for tracking a specific tool call.

        Returns:
            str: The tool_id used for this operation.
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
