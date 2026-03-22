import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useChat } from "@/hooks/useChat";
import type { StreamEvent } from "@/types";
import { chatStream } from "@/lib/api";

vi.mock("@/lib/api", () => ({
  chatStream: vi.fn(),
}));

const chatStreamMock = vi.mocked(chatStream);

describe("useChat", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("streams deltas into assistant message and marks done", async () => {
    chatStreamMock.mockImplementation(async (_messages, onChunk) => {
      onChunk({ type: "status", message: "Planning" });
      onChunk({ type: "text_delta", content: "Hel" });
      onChunk({ type: "text_delta", content: "lo" });
      await Promise.resolve();
      onChunk({ type: "done" });
    });

    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage("hello");
    });

    await waitFor(() => {
      expect(result.current.messages).toHaveLength(2);
      expect(result.current.messages[1].content).toBe("Hello");
      expect(result.current.messages[1].isStreaming).toBe(false);
      expect(result.current.isLoading).toBe(false);
    });
  });

  it("records status and tool status reasoning steps", async () => {
    const toolStatus: StreamEvent = {
      type: "tool_status",
      tool_id: "t1",
      step_number: 1,
      agent: "Planner",
      tool_name: "plan",
      status: "completed",
      input: "Analyze query",
      output: "Plan ready",
    };

    chatStreamMock.mockImplementation(async (_messages, onChunk) => {
      onChunk({ type: "status", message: "Planning" });
      onChunk(toolStatus);
      onChunk({ type: "done" });
    });

    const { result } = renderHook(() => useChat());

    await act(async () => {
      await result.current.sendMessage("hello");
    });

    const assistant = result.current.messages[1];
    expect(assistant.reasoning_steps).toBeDefined();
    expect(assistant.reasoning_steps?.some((s) => s.input === "Planning")).toBe(true);
    expect(assistant.reasoning_steps?.some((s) => s.tool_id === "t1")).toBe(true);
  });

  it("aborts in-flight stream when stopGeneration is called", async () => {
    let capturedSignal: AbortSignal | undefined;

    chatStreamMock.mockImplementation(
      async (_messages, _onChunk, signal?: AbortSignal) => {
        capturedSignal = signal;
        await new Promise<void>((resolve) => {
          signal?.addEventListener("abort", () => resolve(), { once: true });
        });
      },
    );

    const { result } = renderHook(() => useChat());

    await act(async () => {
      void result.current.sendMessage("stop me");
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(true);
    });

    act(() => {
      result.current.stopGeneration();
    });

    await waitFor(() => {
      expect(capturedSignal?.aborted).toBe(true);
      expect(result.current.isLoading).toBe(false);
    });
  });
});
