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

  it("shows copy action after streaming completes", () => {
    render(<MessageActions message={baseMessage} isUser={false} isStreaming={false} />);

    expect(screen.getByTitle("Copy message")).toBeInTheDocument();
  });
});
