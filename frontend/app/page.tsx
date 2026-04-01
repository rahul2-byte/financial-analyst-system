"use client";

import React from "react";
import { useChat } from "@/hooks/useChat";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { ChatInput } from "@/components/chat/ChatInput";
import { Activity } from "lucide-react";

export default function Home() {
  const { messages, isLoading, sendMessage, stopGeneration } = useChat();

  return (
    <main className="app flex h-screen flex-col bg-bg-primary text-text-primary overflow-hidden font-sans">
      {/* Header */}
      <header className="sticky top-0 z-50 flex h-14 items-center justify-between border-b border-border-blueprint bg-bg-primary/80 px-6 backdrop-blur-xl">
        <div className="flex items-center gap-2.5 group cursor-default">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-accent/10 border border-accent/20 text-accent group-hover:bg-accent group-hover:text-white transition-all duration-300">
            <Activity size={18} strokeWidth={2.5} />
          </div>
          <span className="text-sm font-bold tracking-tight text-text-primary group-hover:text-white">FinAI Intelligence</span>
        </div>
        
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 rounded-full bg-bg-secondary border border-border-subtle px-3 py-1 text-[11px] font-bold text-text-secondary shadow-inner tracking-tight">
            <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse-live" />
            LIVE ANALYSIS
          </div>
        </div>
      </header>

      {/* Chat Area / Layout Structure */}
      <div className="chat-layout relative flex flex-1 flex-col overflow-hidden">
        {/* Message Viewport (Independent Scrolling) */}
        <ChatWindow messages={messages} onPromptSelect={sendMessage} />
        
        {/* Chat Input (Sticky Overlay) */}
        <div className="absolute bottom-0 left-0 right-0 z-40 bg-gradient-to-t from-bg-primary via-bg-primary/95 to-transparent pt-12 pointer-events-none">
          <div className="pointer-events-auto">
            <ChatInput 
              onSend={sendMessage} 
              isLoading={isLoading} 
              onStop={stopGeneration}
            />
          </div>
        </div>
      </div>
    </main>
  );
}
