"use client";

import React, { useEffect, useRef, useState } from "react";
import { Message } from "@/types";
import { MessageItem } from "./MessageItem";
import { Activity, ArrowDown } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { motion, AnimatePresence } from "framer-motion";
import { useVirtualizer } from "@tanstack/react-virtual";

interface ChatWindowProps {
  messages: Message[];
  onPromptSelect?: (prompt: string) => void;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ messages, onPromptSelect }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showScrollButton, setShowScrollButton] = useState(false);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);

  // eslint-disable-next-line react-hooks/incompatible-library
  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 150,
    overscan: 5,
  });

  // Robust scrolling function
  const scrollToBottom = (instant = false) => {
    if (!scrollRef.current) return;
    
    if (messages.length > 0) {
      virtualizer.scrollToIndex(messages.length - 1, {
        align: "end",
        behavior: instant ? "auto" : "smooth",
      });
    }
    setShouldAutoScroll(true);
  };

  const lastMessage = messages[messages.length - 1];
  const isStreaming = !!lastMessage?.isStreaming;

  // Improved auto-scroll effect
  useEffect(() => {
    if (shouldAutoScroll && messages.length > 0) {
      virtualizer.scrollToIndex(messages.length - 1, {
        align: "end",
        behavior: isStreaming ? "auto" : "smooth",
      });
    }
  }, [messages.length, lastMessage?.content, shouldAutoScroll, virtualizer, isStreaming]);

  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    const target = e.currentTarget;
    // Check if user is near bottom (with a buffer)
    const threshold = 150;
    const isNearBottom = target.scrollHeight - target.scrollTop <= target.clientHeight + threshold;
    
    setShouldAutoScroll(isNearBottom);
    setShowScrollButton(!isNearBottom && target.scrollTop > 500);
  };

  return (
    <div 
      ref={scrollRef}
      onScroll={handleScroll}
      className="messages-container flex-1 overflow-y-auto scrollbar-none md:scrollbar-thin relative"
    >
      <div className="chat-content mx-auto w-full max-w-3xl pb-[180px] pt-12 px-6">
        {messages.length === 0 ? (
          <div className="flex min-h-[60vh] flex-col items-center justify-center text-center animate-fadeIn">
            <div className="mb-8 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent/10 border border-accent/20 text-accent shadow-[0_0_40px_rgba(139,92,246,0.1)]">
              <Activity size={32} strokeWidth={1.5} />
            </div>
            <div className="mb-3 text-3xl font-bold tracking-tight text-text-primary text-balance">FinAI Intelligence</div>
            <p className="max-w-md text-balance text-base text-text-secondary leading-relaxed opacity-80">
              Your professional analyst for market trends, sector risks, and 
              intelligence reporting.
            </p>
            
            <div className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-3 w-full max-w-lg px-4">
              {[
                "Compare Tech vs Energy risk", 
                "Analyze NVIDIA 5yr trend", 
                "Sector volatility report", 
                "Portfolio stress test"
              ].map((prompt) => (
                <button 
                  key={prompt} 
                  onClick={() => onPromptSelect?.(prompt)}
                  className="p-4 rounded-xl border border-border-subtle bg-bg-secondary text-sm font-medium text-text-secondary hover:border-accent/40 hover:bg-accent/5 hover:text-text-primary transition-all text-left group"
                >
                  <span className="opacity-70 group-hover:opacity-100">{prompt}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div 
            className="relative w-full"
            style={{ height: `${virtualizer.getTotalSize()}px` }}
          >
            {virtualizer.getVirtualItems().map((virtualItem) => (
              <MessageItem 
                key={virtualItem.key} 
                ref={virtualizer.measureElement}
                data-index={virtualItem.index}
                message={messages[virtualItem.index]} 
                className="absolute top-0 left-0 w-full"
                style={{
                  transform: `translateY(${virtualItem.start}px)`,
                }}
              />
            ))}
          </div>
        )}
      </div>

      <AnimatePresence>
        {showScrollButton && (
          <motion.div
            initial={{ opacity: 0, y: 10, scale: 0.9 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.9 }}
            className="fixed bottom-36 right-1/2 translate-x-[384px] z-50 hidden xl:block"
          >
            <Button
              size="sm"
              variant="secondary"
              onClick={() => scrollToBottom()}
              className="h-10 w-10 rounded-full border border-border-subtle bg-bg-secondary shadow-xl hover:bg-accent/10 hover:border-accent/30 text-text-primary group"
            >
              <ArrowDown size={18} className="group-hover:translate-y-0.5 transition-transform" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
