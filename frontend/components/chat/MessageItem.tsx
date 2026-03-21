"use client";

import React from "react";
import { format } from "date-fns";
import { motion, useReducedMotion, type HTMLMotionProps } from "framer-motion";
import { Message } from "@/types";
import { ChartWidget } from "@/components/viz/ChartWidget";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { MessageActions } from "@/components/chat/MessageActions";
import { cn } from "@/lib/utils";

interface MessageItemProps extends React.HTMLAttributes<HTMLDivElement> {
  message: Message;
}

export const MessageItem = React.memo(React.forwardRef<HTMLDivElement, MessageItemProps>(
  function MessageItem({ message, className, ...props }, ref) {
    const isUser = message.role === "user";
    const shouldReduceMotion = useReducedMotion();

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

