import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ReasoningTimeline } from "@/components/chat/ReasoningTimeline";

describe("ReasoningTimeline", () => {
  it("renders running/completed/error steps", () => {
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

    expect(screen.getByText("Reasoning Process")).toBeInTheDocument();
    expect(screen.getByLabelText("Running")).toBeInTheDocument();
    expect(screen.getByLabelText("Completed")).toBeInTheDocument();
    expect(screen.getByLabelText("Error")).toBeInTheDocument();
    expect(screen.getByText("Found 5 sources")).toBeInTheDocument();
  });
});
