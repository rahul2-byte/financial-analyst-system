import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ChatInput } from "@/components/chat/ChatInput";

describe("ChatInput", () => {
  it("sends message on Enter and clears input", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();

    render(<ChatInput onSend={onSend} isLoading={false} />);

    const input = screen.getByPlaceholderText("Analyze market trends, compare sectors...");
    await user.type(input, "Analyze TCS{enter}");

    expect(onSend).toHaveBeenCalledWith("Analyze TCS");
    expect((input as HTMLTextAreaElement).value).toBe("");
  });

  it("does not send while loading", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();

    render(<ChatInput onSend={onSend} isLoading={true} />);

    const input = screen.getByPlaceholderText("Analyze market trends, compare sectors...");
    expect(input).toBeDisabled();
    expect(screen.getByTitle("Stop generating")).toBeInTheDocument();

    await user.type(input, "blocked");
    expect(onSend).not.toHaveBeenCalled();
  });
});
