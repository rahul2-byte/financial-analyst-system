import { useState, useCallback, useRef } from "react";
import { Message, StreamEvent } from "@/types";
import { chatStream } from "@/lib/api";
import { applyStreamEventToMessage } from "@/state/chat/messageReducer";

const CHAT_DEBUG = process.env.NEXT_PUBLIC_CHAT_DEBUG === "true";

function debugLog(...args: unknown[]) {
  if (CHAT_DEBUG) {
    console.log("[useChat]", ...args);
  }
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
    debugLog("sendMessage called", content);
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
      debugLog("Calling chatStream");
      
      await chatStream(
        historyForApi,
        (event: StreamEvent) => {
          debugLog("Received event", event.type);

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

            const updatedMsg = applyStreamEventToMessage(prev[targetIndex], event);

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
