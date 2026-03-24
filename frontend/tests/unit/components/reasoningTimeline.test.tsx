import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect } from "vitest";
import { ReasoningTimeline } from "@/components/chat/ReasoningTimeline";

describe("ReasoningTimeline", () => {
  it("shows concise overview and supports deep logs tab", async () => {
    const user = userEvent.setup();

    render(
      <ReasoningTimeline
        steps={[
          {
            tool_id: "1",
            step_number: 1,
            agent: "Planner",
            tool_name: "Plan",
            status: "running",
            input: "Understand query",
          },
          {
            tool_id: "2",
            step_number: 2,
            agent: "Retriever",
            tool_name: "Retrieve",
            status: "completed",
            input: "Fetch context",
            output: "Found 5 sources",
          },
          {
            tool_id: "3",
            step_number: 3,
            agent: "Validator",
            tool_name: "Validate",
            status: "error",
            input: "Verify numbers",
          },
        ]}
      />,
    );

    expect(screen.getByText("Reasoning")).toBeInTheDocument();
    expect(screen.getByText("Execution Summary")).toBeInTheDocument();
    expect(screen.getByText("Planning")).toBeInTheDocument();
    expect(screen.getByText("Validation")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Deep Logs/i }));

    expect(screen.getByLabelText("Running")).toBeInTheDocument();
    expect(screen.getByLabelText("Completed")).toBeInTheDocument();
    expect(screen.getByLabelText("Error")).toBeInTheDocument();
    expect(screen.getAllByText("Action:").length).toBeGreaterThan(0);
  });
});
