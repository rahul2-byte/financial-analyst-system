import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MessageActions } from "@/components/chat/MessageActions";
import type { Message } from "@/types";

const baseMessage: Message = {
  id: "m1",
  role: "assistant",
  content: "Final answer",
  timestamp: new Date(),
};

describe("MessageActions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("hides actions while streaming", () => {
    render(<MessageActions message={baseMessage} isUser={false} isStreaming={true} />);

    expect(screen.queryByTitle("Copy message")).not.toBeInTheDocument();
  });

  it("shows assistant action controls after streaming completes", () => {
    render(<MessageActions message={baseMessage} isUser={false} isStreaming={false} />);

    expect(screen.getByTitle("Helpful")).toBeInTheDocument();
    expect(screen.getByTitle("Not helpful")).toBeInTheDocument();
    expect(screen.getByTitle("Copy message")).toBeInTheDocument();
    expect(screen.getByTitle("Regenerate")).toBeInTheDocument();
  });
});
