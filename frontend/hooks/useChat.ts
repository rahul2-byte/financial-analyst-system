import { useState, useCallback, useRef, useOptimistic } from "react";
import { Message, StreamEvent } from "@/types";
import { chatStream } from "@/lib/api";

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * React 19 useOptimistic hook to show the user's message immediately.
   * NOTE: The UI call to sendMessage should be wrapped in startTransition 
   * (e.g., from React 19's useTransition) to trigger this optimistic update.
   */
  const [optimisticMessages, addOptimisticMessage] = useOptimistic<Message[], Message>(
    messages,
    (state, newMessage) => [...state, newMessage]
  );

  // Keep a ref to messages for history construction to avoid recreating sendMessage on every token
  const messagesRef = useRef<Message[]>(messages);
  messagesRef.current = messages;

  const sendMessage = useCallback(async (content: string) => {
    console.log("sendMessage called with content:", content);
    if (!content.trim() || isLoading) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      timestamp: new Date(),
    };

    // Optimistically show the user message
    addOptimisticMessage(userMessage);

    const assistantMessageId = crypto.randomUUID();
    console.log("Created assistantMessageId:", assistantMessageId);
    const assistantMessagePlaceholder: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      charts: [],
      timestamp: new Date(),
      isStreaming: true,
    };

    // Update real state immediately with both the user message and assistant placeholder
    setMessages((prev) => [...prev, userMessage, assistantMessagePlaceholder]);
    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      // Use messages history from ref at the point of sending
      const historyForApi = [...messagesRef.current, userMessage];
      
      console.log("useChat: Starting stream for assistantMessageId:", assistantMessageId);
      
      await chatStream(
        historyForApi,
        (event: StreamEvent) => {
          console.log("useChat: Received event:", event.type, event.message || "");
          
          setMessages((prev) => {
            // EFFICIENT UPDATE: Check the last message first
            const lastIndex = prev.length - 1;
            const targetIndex = (prev[lastIndex]?.id === assistantMessageId) 
              ? lastIndex 
              : prev.findIndex((m) => m.id === assistantMessageId);

            if (targetIndex === -1) return prev;

            const currentMsg = prev[targetIndex];
            const updatedMsg = { ...currentMsg };

            if (event.type === "text_delta") {
              updatedMsg.content = (updatedMsg.content || "") + (event.content || "");
            } else if (event.type === "chart") {
              updatedMsg.charts = [...(updatedMsg.charts || []), event.content];
            } else if (event.type === "status") {
              // Update content with a "status" indicator if it's currently empty
              if (!updatedMsg.content) {
                // We'll keep status internal or show it subtly
                console.log("useChat: Agent Status Update:", event.message);
              }
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
      console.log("useChat: Stream completed successfully");
    } catch (error) {
      console.error("Chat hook error:", error);
    } finally {
      console.log("useChat: In finally block, cleaning up isLoading");
      if (abortControllerRef.current === controller) {
        setIsLoading(false);
        abortControllerRef.current = null;
        
        setMessages((prev) => {
          const lastIndex = prev.length - 1;
          const targetIndex = (prev[lastIndex]?.id === assistantMessageId) 
            ? lastIndex 
            : prev.findIndex((m) => m.id === assistantMessageId);

          if (targetIndex !== -1 && prev[targetIndex].isStreaming) {
             console.log("useChat: Finalizing isStreaming for assistant message");
             const next = [...prev];
             next[targetIndex] = { ...next[targetIndex], isStreaming: false };
             return next;
          }
          return prev;
        });
      }
    }
  }, [isLoading, addOptimisticMessage]);

  const stopGeneration = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
      
      // Mark last message as not streaming efficiently
      setMessages((prev) => {
        if (prev.length === 0) return prev;
        const lastIndex = prev.length - 1;
        const lastMsg = prev[lastIndex];
        if (lastMsg && lastMsg.role === "assistant" && lastMsg.isStreaming) {
          const next = [...prev];
          next[lastIndex] = { ...lastMsg, isStreaming: false };
          return next;
        }
        return prev;
      });
    }
  }, []);

  return {
    messages: optimisticMessages, // Return optimistic state
    isLoading,
    sendMessage,
    stopGeneration,
  };
}

