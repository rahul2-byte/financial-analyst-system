import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";

describe("MarkdownRenderer", () => {
  it("renders plain text while streaming to keep updates smooth", () => {
    render(<MarkdownRenderer content={"**bold** streaming"} isStreaming={true} />);

    expect(screen.getByText("**bold** streaming")).toBeInTheDocument();
  });

  it("renders markdown after streaming completes", () => {
    const { container } = render(<MarkdownRenderer content={"**bold** done"} isStreaming={false} />);

    const strong = container.querySelector("strong");
    expect(strong).toBeTruthy();
    expect(strong?.textContent).toBe("bold");
  });
});
