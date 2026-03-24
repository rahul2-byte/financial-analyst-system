import { useState, useCallback, useRef } from "react";
import { Message, StreamEvent, ToolStatus } from "@/types";
import { chatStream } from "@/lib/api";

const STATUS_NOISE_PATTERNS: RegExp[] = [
  /^Executing:/i,
  /^Step\s+\d+:\s+.+\s+running\.{0,3}$/i,
  /^Step\s+\d+:\s+.+\s+completed\.{0,3}$/i,
];

const STATUS_PRIORITY_PATTERNS: RegExp[] = [
  /initializing/i,
  /planning/i,
  /synthesizing|synthesis/i,
  /verifying|verification/i,
  /compliance/i,
  /failed|error|crashed/i,
];

function shouldDisplayStatus(message: string): boolean {
  const isPriority = STATUS_PRIORITY_PATTERNS.some((pattern) => pattern.test(message));
  if (isPriority) return true;
  return !STATUS_NOISE_PATTERNS.some((pattern) => pattern.test(message));
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const pendingTextRef = useRef("");
  const flushHandleRef = useRef<number | null>(null);

  // Keep a ref to messages for history construction
  const messagesRef = useRef<Message[]>(messages);
  messagesRef.current = messages;

  const sendMessage = useCallback(async (content: string) => {
    console.log("[useChat] sendMessage called:", content);
    if (!content.trim() || isLoading) return;

    // Use a robust UUID generator fallback for non-secure contexts
    const generateId = () => {
      if (typeof crypto !== "undefined" && crypto.randomUUID) {
        return crypto.randomUUID();
      }
      return Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
    };

    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content,
      timestamp: new Date(),
    };

    const assistantMessageId = generateId();
    const assistantMessagePlaceholder: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      charts: [],
      reasoning_steps: [],
      timestamp: new Date(),
      isStreaming: true,
    };

    // Update state immediately
    setMessages((prev) => [...prev, userMessage, assistantMessagePlaceholder]);
    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    const flushPendingText = () => {
      const delta = pendingTextRef.current;
      if (!delta) return;

      pendingTextRef.current = "";
      setMessages((prev) => {
        const targetIndex = prev.findIndex((m) => m.id === assistantMessageId);
        if (targetIndex === -1) return prev;

        const next = [...prev];
        const updatedMsg = { ...next[targetIndex] };
        updatedMsg.content = (updatedMsg.content || "") + delta;
        next[targetIndex] = updatedMsg;
        return next;
      });
    };

    const scheduleFlush = () => {
      if (flushHandleRef.current !== null) return;

      // Use timer-based batching instead of requestAnimationFrame.
      // requestAnimationFrame can be heavily throttled in background/inactive tabs,
      // which makes streamed text appear all at once when focus returns.
      flushHandleRef.current = window.setTimeout(() => {
        flushHandleRef.current = null;
        flushPendingText();
      }, 16);
    };

    const cancelScheduledFlush = () => {
      if (flushHandleRef.current === null) return;
      clearTimeout(flushHandleRef.current);
      flushHandleRef.current = null;
    };

    try {
      const historyForApi = [...messagesRef.current, userMessage];
      console.log("[useChat] Calling chatStream...");
      
      await chatStream(
        historyForApi,
        (event: StreamEvent) => {
          console.log(`[useChat] Received event: ${event.type}`);

          if (event.type === "text_delta") {
            pendingTextRef.current += event.content || "";
            scheduleFlush();
            return;
          }

          // Keep text visually smooth by flushing queued deltas before non-text events.
          flushPendingText();
          
          setMessages((prev) => {
            const targetIndex = prev.findIndex((m) => m.id === assistantMessageId);
            if (targetIndex === -1) return prev;

            const updatedMsg = { ...prev[targetIndex] };

            if (event.type === "chart") {
              const chartPayload = {
                title: event.title,
                chartType: event.chartType,
                data: event.data,
                xAxisKey: event.xAxisKey,
                seriesKeys: event.seriesKeys,
              };
              updatedMsg.charts = [...(updatedMsg.charts || []), chartPayload];
            } else if (event.type === "status") {
              const statusMessage = event.message?.trim() || "";
              if (!statusMessage || !shouldDisplayStatus(statusMessage)) {
                return prev;
              }

              // Add generic status updates to reasoning steps for immediate feedback
              const steps = [...(updatedMsg.reasoning_steps || [])];
              // Only add if not already present
              if (!steps.find(s => s.input === statusMessage)) {
                steps.push({
                  tool_id: `status-${steps.length}`,
                  step_number: -1, // Use -1 to keep system status at top
                  agent: "System",
                  tool_name: "Orchestrator",
                  status: "completed",
                  input: statusMessage,
                });
                updatedMsg.reasoning_steps = steps;
              }
            } else if (event.type === "tool_status") {
              const stepData: ToolStatus = {
                tool_id: event.tool_id,
                step_number: event.step_number,
                agent: event.agent,
                tool_name: event.tool_name,
                status: event.status,
                input: event.input,
                output: event.output,
              };
              const steps = [...(updatedMsg.reasoning_steps || [])];
              const existingIndex = steps.findIndex((s) => s.tool_id === stepData.tool_id);
              
              if (existingIndex !== -1) {
                steps[existingIndex] = { ...steps[existingIndex], ...stepData };
              } else {
                steps.push(stepData as ToolStatus);
              }
              updatedMsg.reasoning_steps = steps.sort((a, b) => a.step_number - b.step_number);
            } else if (event.type === "done") {
              updatedMsg.isStreaming = false;
            } else if (event.type === "error") {
              const errorMessage = event.message || event.content || "Unknown error";
              updatedMsg.content = (updatedMsg.content || "") + `\n\n*Error: ${errorMessage}*`;
              updatedMsg.isStreaming = false;
            }

            const next = [...prev];
            next[targetIndex] = updatedMsg;
            return next;
          });
        },
        controller.signal
      );
    } catch (error) {
      console.error("[useChat] Stream error:", error);
    } finally {
      cancelScheduledFlush();
      flushPendingText();
      setIsLoading(false);
      abortControllerRef.current = null;
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.id === assistantMessageId);
        if (idx !== -1) {
          const next = [...prev];
          next[idx] = { ...next[idx], isStreaming: false };
          return next;
        }
        return prev;
      });
    }
  }, [isLoading]);

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  }, []);

  return {
    messages,
    isLoading,
    sendMessage,
    stopGeneration,
  };
}
