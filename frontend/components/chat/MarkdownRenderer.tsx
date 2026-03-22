"use client";

import React, { memo, useMemo } from "react";
import ReactMarkdown, { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "@/components/chat/CodeBlock";
import { cn } from "@/lib/utils";

interface MarkdownRendererProps {
  content: string;
  isStreaming?: boolean;
  ref?: React.Ref<HTMLDivElement>;
}

const REMARK_PLUGINS = [remarkGfm];

export const MarkdownRenderer = memo(({ content, isStreaming, ref }: MarkdownRendererProps) => {
  const components: Components = useMemo(() => ({
    pre({ children }) {
      // Remove the default <pre> wrapper to prevent double boxing
      return <>{children}</>;
    },
    code(props) {
      const { children, className, ...rest } = props;
      const match = /language-(\w+)/.exec(className || "");
      return match ? (
        <CodeBlock
          code={String(children).replace(/\n$/, "")}
          language={match[1]}
        />
      ) : (
        <code
          className={cn(
            "bg-accent/10 text-accent px-1.5 py-0.5 rounded text-[14px] font-mono",
            className
          )}
          {...rest}
        >
          {children}
        </code>
      );
    },
    table({ children }) {
      return (
        <div className="my-8 w-full overflow-x-auto rounded-lg border border-border-blueprint bg-bg-secondary/20 shadow-sm">
          <table className="w-full border-collapse text-left text-[14px]">
            {children}
          </table>
        </div>
      );
    },
    thead({ children }) {
      return (
        <thead className="bg-bg-secondary/50 border-b border-border-blueprint text-text-primary uppercase text-[11px] font-bold tracking-widest">
          {children}
        </thead>
      );
    },
    th({ children }) {
      return <th className="px-4 py-3 text-text-primary">{children}</th>;
    },
    td({ children }) {
      const contentString = (Array.isArray(children) ? children[0] : children)?.toString() || "";
      const cleanString = contentString.replace(/[,%$]/g, "").trim();
      const isNumerical = cleanString !== "" && !isNaN(Number(cleanString));

      return (
        <td className={cn(
          "px-4 py-3 border-b-[0.5px] border-white/5",
          isNumerical ? "font-mono tabular-nums text-emerald-400/90" : "text-text-secondary"
        )}>
          {children}
        </td>
      );
    },
    tr({ children }) {
      return (
        <tr className="hover:bg-white/5 transition-colors duration-150">
          {children}
        </tr>
      );
    },
  }), []);

  return (
    <div ref={ref} className="prose prose-invert max-w-none">
      {content === "" && isStreaming ? (
        <div className="flex gap-1 py-2 px-1">
          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-text-secondary"></span>
          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-text-secondary"></span>
          <span className="typing-dot h-1.5 w-1.5 rounded-full bg-text-secondary"></span>
        </div>
      ) : isStreaming ? (
        <div className="whitespace-pre-wrap break-words leading-7 text-text-primary">
          {content}
          <span className="inline-block w-1.5 h-4 ml-1 bg-accent/50 animate-pulse align-middle" />
        </div>
      ) : (
        <ReactMarkdown
          remarkPlugins={REMARK_PLUGINS}
          components={components}
        >
          {content}
        </ReactMarkdown>
      )}
    </div>
  );
});

MarkdownRenderer.displayName = "MarkdownRenderer";
