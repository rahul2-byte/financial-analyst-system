"use client";

import React, { useRef, useState, useEffect, useTransition, startTransition } from "react";
import { StopCircle, ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading: boolean;
  onStop?: () => void;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSend, isLoading, onStop }) => {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 240)}px`;
    }
  }, [input]);

  const handleSend = () => {
    if (!input.trim() || isLoading) return;
    
    // Fix: React 19 useOptimistic must be wrapped in startTransition
    startTransition(() => {
      onSend(input);
    });
    
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-input-wrapper relative mx-auto w-full max-w-3xl px-6 pb-12 pt-2">
      <div 
        className={cn(
          "chat-input relative flex flex-col gap-2 rounded-[24px] border bg-white/5 backdrop-blur-xl p-2 shadow-[0_10px_40px_-10px_rgba(0,0,0,0.5)] transition-all duration-300 focus-within:border-accent/40 focus-within:ring-4 focus-within:ring-accent/5",
          isLoading ? "border-border-blueprint" : "border-border-blueprint hover:border-border-blueprint/80"
        )}
      >
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Analyze market trends, compare sectors..."
          className="min-h-[56px] w-full resize-none border-0 bg-transparent px-4 py-4 text-[15px] leading-relaxed text-text-primary placeholder:text-text-secondary placeholder:opacity-50 focus-visible:ring-0"
          disabled={isLoading}
          rows={1}
        />
        
        <div className="flex items-center justify-between px-3 pb-2">
          <div className="flex gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-accent/5 text-accent/60 hover:text-accent hover:bg-accent/10 transition-colors cursor-pointer border border-accent/10 shadow-inner">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            {isLoading && (
              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-accent/10 border border-accent/20">
                <span className="h-1.5 w-1.5 rounded-full bg-accent animate-pulse" />
                <span className="text-[10px] font-bold text-accent tracking-wider uppercase">Analyzing</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            <AnimatePresence mode="wait">
              {isLoading ? (
                <motion.div
                  key="stop"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                >
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={onStop}
                    className="h-10 w-10 rounded-xl bg-accent p-0 text-white hover:bg-accent-hover shadow-md shadow-accent/10 border border-accent/20"
                    title="Stop generating"
                  >
                    <StopCircle size={20} fill="currentColor" />
                  </Button>
                </motion.div>
              ) : (
                <motion.div
                  key="send"
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                >
                  <Button
                    size="sm"
                    onClick={handleSend}
                    disabled={!input.trim()}
                    className={cn(
                      "send-button h-10 w-10 rounded-xl p-0 transition-all duration-300 border",
                      input.trim() 
                        ? "bg-accent text-white shadow-md shadow-accent/10 border-accent/20 hover:bg-accent-hover hover:scale-[1.02]" 
                        : "bg-white/5 text-white/20 border-white/5"
                    )}
                  >
                    <ArrowUp size={22} strokeWidth={3} />
                  </Button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
};
