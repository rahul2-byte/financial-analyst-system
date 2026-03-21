"use client";

import React, { useState, useCallback } from "react";
import { Message } from "@/types";
import { Copy, RotateCcw, ThumbsUp, ThumbsDown } from "lucide-react";

interface MessageActionsProps {
  message: Message;
  isUser: boolean;
  isStreaming: boolean;
}

export const MessageActions = React.memo(({ message, isUser, isStreaming }: MessageActionsProps) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  }, [message.content]);

  // Actions Bar
  if (isStreaming || message.content === "") {
    return null;
  }

  return (
    <div className="message-actions flex gap-1 mt-6 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity duration-200 border-t border-border-subtle/20 pt-4">
      {!isUser && (
        <>
          <ActionButton icon={<ThumbsUp size={14} />} title="Helpful" />
          <ActionButton icon={<ThumbsDown size={14} />} title="Not helpful" />
        </>
      )}
      <ActionButton 
        icon={copied ? <span className="text-[10px] font-bold">COPIED</span> : <Copy size={14} />} 
        title="Copy message" 
        onClick={handleCopy} 
      />
      {!isUser && <ActionButton icon={<RotateCcw size={14} />} title="Regenerate" />}
    </div>
  );
});

MessageActions.displayName = "MessageActions";

const ActionButton = ({ icon, title, onClick, label }: { icon: React.ReactNode, title: string, label?: string, onClick?: () => void }) => (
  <button 
    type="button"
    onClick={onClick}
    aria-label={label || title}
    className="h-8 min-w-[32px] px-2 flex items-center justify-center rounded-lg bg-bg-secondary border border-border-subtle text-text-secondary hover:text-text-primary hover:border-accent/40 hover:bg-accent/5 transition-all shadow-sm"
    title={title}
  >
    {icon}
  </button>
);
