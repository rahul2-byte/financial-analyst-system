"use client";

import React, { useState, useEffect, useRef } from "react";
import { Check, Copy } from "lucide-react";
import { codeToHtml } from "shiki";
import { motion, AnimatePresence } from "framer-motion";

interface CodeBlockProps {
  code: string;
  language?: string;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ code, language = "text" }) => {
  const [highlightedHtml, setHighlightedHtml] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [isHighlighting, setIsHighlighting] = useState(false);
  const highlightTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const highlight = async () => {
      // If code is too long or updates too frequently, we debounce the highlight
      // to keep the main thread free for streaming text.
      if (highlightTimeoutRef.current) {
        clearTimeout(highlightTimeoutRef.current);
      }

      setIsHighlighting(true);

      // Small delay to allow the stream to batch tokens before a heavy re-highlight
      highlightTimeoutRef.current = setTimeout(async () => {
        try {
          const html = await codeToHtml(code, {
            lang: language,
            theme: "github-dark",
          });
          setHighlightedHtml(html);
        } catch (err) {
          console.error("Shiki error:", err);
          setHighlightedHtml(""); // Fallback to raw text
        } finally {
          setIsHighlighting(false);
        }
      }, 100);
    };

    highlight();

    return () => {
      if (highlightTimeoutRef.current) clearTimeout(highlightTimeoutRef.current);
    };
  }, [code, language]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  return (
    <div className="code-block group relative my-6 w-full overflow-hidden rounded-xl border border-border-subtle bg-code-bg shadow-2xl shadow-black/40">
      {/* Header */}
      <div className="code-header flex items-center justify-between border-b border-border-subtle bg-bg-secondary/80 px-4 py-2.5 text-[12px] backdrop-blur-sm">
        <span className="font-mono text-text-secondary opacity-80 uppercase tracking-widest text-[10px]">
          {language}
        </span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-text-secondary transition-all hover:bg-white/5 hover:text-text-primary"
        >
          <AnimatePresence mode="wait">
            {copied ? (
              <motion.span
                key="check"
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.8, opacity: 0 }}
                className="flex items-center gap-1.5 text-emerald-400 font-bold"
              >
                <Check size={12} strokeWidth={3} />
                <span className="tracking-tighter uppercase text-[10px]">Copied</span>
              </motion.span>
            ) : (
              <motion.span
                key="copy"
                initial={{ scale: 0.8, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                exit={{ scale: 0.8, opacity: 0 }}
                className="flex items-center gap-1.5 font-bold"
              >
                <Copy size={12} strokeWidth={2.5} />
                <span className="tracking-tighter uppercase text-[10px]">Copy code</span>
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>

      {/* Code Area */}
      <div className="code-body relative max-h-[600px] overflow-x-auto p-4 font-mono text-[13px] leading-relaxed scrollbar-thin scrollbar-thumb-zinc-800 scrollbar-track-transparent">
        {highlightedHtml ? (
          <div
            dangerouslySetInnerHTML={{ __html: highlightedHtml }}
            className="shiki-wrapper"
          />
        ) : (
          <pre className="m-0 bg-transparent p-0 border-0">
            <code className="text-text-primary">{code}</code>
          </pre>
        )}
        
        {/* Subtle Indicator for highlighting processing (optional, very minimal) */}
        {isHighlighting && !highlightedHtml && (
          <div className="absolute right-4 top-4 h-1.5 w-1.5 rounded-full bg-accent/30 animate-pulse" />
        )}
      </div>
    </div>
  );
};
