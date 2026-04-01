import { Message, StreamEvent, ToolStatus } from "@/types";
import { shouldDisplayStatus } from "@/state/chat/statusPolicy";

export function applyStreamEventToMessage(message: Message, event: StreamEvent): Message {
  const updated = { ...message };

  if (event.type === "chart") {
    const chartPayload = {
      title: event.title,
      chartType: event.chartType,
      data: event.data,
      xAxisKey: event.xAxisKey,
      seriesKeys: event.seriesKeys,
    };
    updated.charts = [...(updated.charts || []), chartPayload];
    return updated;
  }

  if (event.type === "status") {
    const statusMessage = event.message?.trim() || "";
    if (!statusMessage || !shouldDisplayStatus(statusMessage)) {
      return message;
    }

    const steps = [...(updated.reasoning_steps || [])];
    if (!steps.find((step) => step.input === statusMessage)) {
      steps.push({
        tool_id: `status-${steps.length}`,
        step_number: -1,
        agent: "System",
        tool_name: "Orchestrator",
        status: "completed",
        input: statusMessage,
      });
      updated.reasoning_steps = steps;
    }
    return updated;
  }

  if (event.type === "tool_status") {
    const stepData: ToolStatus = {
      tool_id: event.tool_id,
      step_number: event.step_number,
      agent: event.agent,
      tool_name: event.tool_name,
      status: event.status,
      input: event.input,
      output: event.output,
    };
    const steps = [...(updated.reasoning_steps || [])];
    const existingIndex = steps.findIndex((step) => step.tool_id === stepData.tool_id);

    if (existingIndex !== -1) {
      steps[existingIndex] = { ...steps[existingIndex], ...stepData };
    } else {
      steps.push(stepData);
    }

    updated.reasoning_steps = steps.sort((a, b) => a.step_number - b.step_number);
    return updated;
  }

  if (event.type === "done") {
    updated.isStreaming = false;
    return updated;
  }

  if (event.type === "error") {
    const errorMessage = event.message || event.content || "Unknown error";
    updated.content = (updated.content || "") + `\n\n*Error: ${errorMessage}*`;
    updated.isStreaming = false;
    return updated;
  }

  return updated;
}
