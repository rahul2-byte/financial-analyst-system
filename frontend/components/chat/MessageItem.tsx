"use client";

import React, { useState } from "react";
import { format } from "date-fns";
import { motion, useReducedMotion, type HTMLMotionProps, AnimatePresence } from "framer-motion";
import { Brain, ChevronDown, Loader2 } from "lucide-react";
import { Message } from "@/types";
import { ChartWidget } from "@/components/viz/ChartWidget";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { MessageActions } from "@/components/chat/MessageActions";
import { ReasoningTimeline } from "@/components/chat/ReasoningTimeline";
import { cn } from "@/lib/utils";

interface MessageItemProps extends React.HTMLAttributes<HTMLDivElement> {
  message: Message;
}

export const MessageItem = React.memo(React.forwardRef<HTMLDivElement, MessageItemProps>(
  function MessageItem({ message, className, ...props }, ref) {
    const isUser = message.role === "user";
    const shouldReduceMotion = useReducedMotion();
    const [isExpanded, setIsExpanded] = useState(!!message.isStreaming);
    const isReasoningExpanded = Boolean(message.isStreaming) || isExpanded;

    const reasoningSteps = message.reasoning_steps || [];
    const hasReasoning = reasoningSteps.length > 0;
    const reasoningId = `reasoning-${message.id}`;

    const getAnimationProps = (delay: number): HTMLMotionProps<"div"> => {
      if (shouldReduceMotion) return {};
      return {
        initial: { opacity: 0, y: 10 },
        animate: { opacity: 1, y: 0 },
        transition: { duration: 0.3, ease: "easeOut" as const, delay },
      };
    };

    return (
      <div
        ref={ref}
        className={cn(
          "message group flex w-full flex-col mb-12",
          isUser ? "items-end" : "items-center",
          className
        )}
        data-reasoning-count={reasoningSteps.length}
        {...props}
      >
      <div className={cn(
        "flex w-full max-w-3xl gap-4",
        isUser ? "justify-end" : "justify-start"
      )}>
        {/* Message Content Area */}
        <div className={cn(
          "flex flex-col gap-2 w-full",
          isUser ? "items-end max-w-[80%]" : "items-start"
        )}>
          {/* Label & Time */}
          <div className={cn(
            "flex items-center gap-2 mb-1",
            isUser ? "flex-row-reverse" : "flex-row"
          )}>
            <span className="text-[11px] font-bold tracking-wider uppercase text-text-secondary opacity-70">
              {isUser ? "Query" : "Analysis"}
            </span>
            <span className="text-[10px] font-medium tracking-wide text-text-secondary opacity-70">
              {format(message.timestamp, "HH:mm")}
            </span>
          </div>

          {/* Bubble / Content */}
          <div className={cn(
            "relative w-full transition-all duration-200",
            isUser 
              ? "bg-bg-secondary/30 text-text-primary px-4 py-3 rounded-2xl border border-border-subtle/50 text-right italic" 
              : "bg-transparent text-text-primary px-0 py-0"
          )}>
            {!isUser && hasReasoning && (
              <div className="mb-4">
                <button 
                  onClick={() => setIsExpanded(!isExpanded)}
                  aria-expanded={isReasoningExpanded}
                  aria-controls={reasoningId}
                  className={cn(
                    "flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-all duration-200 group",
                    isReasoningExpanded 
                      ? "bg-bg-secondary/50 border-border-subtle/30" 
                      : "bg-bg-secondary/20 border-border-subtle/10 hover:bg-bg-secondary/40"
                  )}
                >
                  <div className="relative flex items-center justify-center">
                    <Brain className={cn(
                      "h-3.5 w-3.5 transition-colors duration-200",
                      message.isStreaming ? "text-accent-primary animate-pulse" : "text-text-secondary opacity-60"
                    )} />
                    {message.isStreaming && (
                      <Loader2 className="absolute h-3.5 w-3.5 animate-spin text-accent-primary/50 scale-125" />
                    )}
                  </div>
                  
                  <span className="text-xs font-semibold text-text-secondary tracking-tight">
                    {message.isStreaming ? "Reasoning..." : "Methodology"}
                  </span>
                  
                  <div className="flex items-center gap-1.5 ml-1">
                    <span className="h-1 w-1 rounded-full bg-text-secondary/20" />
                    <span className="text-[10px] font-medium text-text-secondary/40">
                      {reasoningSteps.length} {reasoningSteps.length === 1 ? "step" : "steps"}
                    </span>
                  </div>

                    <ChevronDown className={cn(
                      "h-3.5 w-3.5 text-text-secondary opacity-40 transition-transform duration-300 ml-1 group-hover:opacity-80",
                      isReasoningExpanded && "rotate-180"
                    )} />
                </button>

                <AnimatePresence>
                  {isReasoningExpanded && (
                    <motion.div
                      id={reasoningId}
                      initial={{ height: 0, opacity: 0 }}
                      animate={{ height: "auto", opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
                      className="overflow-hidden"
                    >
                      <div className="pt-2 pl-2">
                        <ReasoningTimeline steps={reasoningSteps} />
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            )}

            <motion.div {...getAnimationProps(0)}>
              <MarkdownRenderer content={message.content} isStreaming={message.isStreaming} />
            </motion.div>

            <motion.div {...getAnimationProps(0.1)}>
              <MessageActions 
                message={message} 
                isUser={isUser} 
                isStreaming={!!message.isStreaming} 
              />
            </motion.div>
          </div>

          {/* Charts */}
          {message.charts && message.charts.length > 0 && (
            <motion.div 
              className="mt-6 flex flex-col gap-8 w-full"
              {...getAnimationProps(0.2)}
            >
              {message.charts.map((chart, idx) => (
                <div key={`${message.id}-chart-${idx}`} className="animate-fadeIn border-t border-border-subtle/30 pt-6">
                  <ChartWidget payload={chart} />
                </div>
              ))}
            </motion.div>
          )}
        </div>
      </div>
    </div>
    );
  }
));
