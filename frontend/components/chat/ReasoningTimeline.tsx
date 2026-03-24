"use client";

import React, { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle, AlertTriangle, Loader2, FileText, ListTree } from "lucide-react";
import { ToolStatus } from "@/types";

interface ReasoningTimelineProps {
  steps: ToolStatus[];
}

type ReasoningTab = "overview" | "trace";
type StepState = "running" | "completed" | "error";

interface Milestone {
  key: string;
  title: string;
  status: StepState;
  count: number;
  detail: string;
}

const EMPTY_STEPS: ToolStatus[] = [];

const MILESTONE_ORDER = [
  "planning",
  "data",
  "analysis",
  "validation",
  "synthesis",
  "orchestration",
  "execution",
] as const;

function shortText(input: string, maxLength = 82): string {
  const normalized = input.trim();
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength - 1)}...`;
}

function asStateValue(status: ToolStatus["status"]): StepState {
  if (status === "error") return "error";
  if (status === "running") return "running";
  return "completed";
}

function mergeState(current: StepState, incoming: StepState): StepState {
  if (current === "error" || incoming === "error") return "error";
  if (current === "running" || incoming === "running") return "running";
  return "completed";
}

function milestoneForStep(step: ToolStatus): { key: string; title: string } {
  const agent = step.agent.toLowerCase();
  const tool = step.tool_name.toLowerCase();
  const input = step.input.toLowerCase();

  if (agent.includes("planner") || input.includes("plan")) {
    return { key: "planning", title: "Planning" };
  }

  if (
    agent.includes("market") ||
    agent.includes("retrieval") ||
    agent.includes("web") ||
    tool.includes("search") ||
    tool.includes("ticker") ||
    tool.includes("data")
  ) {
    return { key: "data", title: "Data Collection" };
  }

  if (
    agent.includes("fundamental") ||
    agent.includes("technical") ||
    agent.includes("macro") ||
    agent.includes("sentiment") ||
    agent.includes("contrarian") ||
    input.includes("analysis")
  ) {
    return { key: "analysis", title: "Analysis" };
  }

  if (
    agent.includes("validation") ||
    agent.includes("verification") ||
    input.includes("verify") ||
    input.includes("compliance")
  ) {
    return { key: "validation", title: "Validation" };
  }

  if (input.includes("synthes") || input.includes("final answer")) {
    return { key: "synthesis", title: "Synthesis" };
  }

  if (agent.includes("orchestrator") || agent.includes("system")) {
    return { key: "orchestration", title: "Orchestration" };
  }

  return { key: "execution", title: "Execution" };
}

function getTraceSteps(steps: ToolStatus[]): ToolStatus[] {
  const ordered = [...steps].sort((a, b) => a.step_number - b.step_number);
  const compact: ToolStatus[] = [];

  for (const step of ordered) {
    const previous = compact[compact.length - 1];
    const duplicate =
      previous &&
      previous.agent === step.agent &&
      previous.tool_name === step.tool_name &&
      previous.input === step.input &&
      previous.status === step.status;

    if (!duplicate) {
      compact.push(step);
    }
  }

  return compact;
}

function buildMilestones(steps: ToolStatus[]): Milestone[] {
  const byKey = new Map<string, Milestone>();

  for (const step of steps) {
    const bucket = milestoneForStep(step);
    const incomingState = asStateValue(step.status);
    const existing = byKey.get(bucket.key);

    if (!existing) {
      byKey.set(bucket.key, {
        key: bucket.key,
        title: bucket.title,
        status: incomingState,
        count: 1,
        detail: shortText(step.input),
      });
      continue;
    }

    existing.count += 1;
    existing.status = mergeState(existing.status, incomingState);
    existing.detail = shortText(step.input);
  }

  return Array.from(byKey.values()).sort((a, b) => {
    const aIndex = MILESTONE_ORDER.indexOf(a.key as (typeof MILESTONE_ORDER)[number]);
    const bIndex = MILESTONE_ORDER.indexOf(b.key as (typeof MILESTONE_ORDER)[number]);
    const safeA = aIndex === -1 ? 999 : aIndex;
    const safeB = bIndex === -1 ? 999 : bIndex;
    return safeA - safeB;
  });
}

export const ReasoningTimeline: React.FC<ReasoningTimelineProps> = ({ steps }) => {
  const safeSteps = steps ?? EMPTY_STEPS;

  const [activeTab, setActiveTab] = useState<ReasoningTab>("overview");

  const traceSteps = useMemo(() => getTraceSteps(safeSteps), [safeSteps]);
  const milestones = useMemo(() => buildMilestones(traceSteps), [traceSteps]);

  if (safeSteps.length === 0) return null;

  const completedCount = milestones.filter((m) => m.status === "completed").length;
  const runningCount = milestones.filter((m) => m.status === "running").length;
  const errorCount = milestones.filter((m) => m.status === "error").length;

  const totalMilestones = milestones.length;

  return (
    <div className="flex flex-col gap-2 py-2">
      <div className="flex items-center justify-between gap-3 mb-2 px-1">
        <div className="flex items-center gap-2">
          <div className="h-px w-8 bg-border-subtle/30" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-text-secondary opacity-60">
            Reasoning
          </span>
        </div>

        <div className="inline-flex rounded-lg border border-border-subtle/30 bg-bg-secondary/30 p-0.5">
          <button
            type="button"
            onClick={() => setActiveTab("overview")}
            className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
              activeTab === "overview"
                ? "bg-bg-primary text-text-primary"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            <FileText className="h-3 w-3" />
            Overview
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("trace")}
            className={`inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
              activeTab === "trace"
                ? "bg-bg-primary text-text-primary"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            <ListTree className="h-3 w-3" />
            Deep Logs
          </button>
        </div>
      </div>

      {activeTab === "overview" ? (
        <div className="flex flex-col gap-3">
          <div className="rounded-xl border border-border-subtle/30 bg-bg-secondary/20 px-3 py-2.5">
            <div className="text-[10px] font-bold uppercase tracking-widest text-text-secondary/70">
              Execution Summary
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-emerald-300">
                Completed {completedCount}/{totalMilestones}
              </span>
              {runningCount > 0 && (
                <span className="rounded-full border border-sky-500/30 bg-sky-500/10 px-2 py-1 text-sky-300">
                  Running {runningCount}
                </span>
              )}
              {errorCount > 0 && (
                <span className="rounded-full border border-red-500/30 bg-red-500/10 px-2 py-1 text-red-300">
                  Errors {errorCount}
                </span>
              )}
              <span className="rounded-full border border-border-subtle/40 bg-bg-primary/40 px-2 py-1 text-text-secondary">
                Events {traceSteps.length}
              </span>
            </div>
          </div>

          <div className="space-y-2">
            {milestones.map((milestone) => (
              <div
                key={milestone.key}
                className="rounded-lg border border-border-subtle/20 bg-bg-secondary/15 px-3 py-2"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    {milestone.status === "running" ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-300" />
                    ) : milestone.status === "error" ? (
                      <AlertTriangle className="h-3.5 w-3.5 text-red-300" />
                    ) : (
                      <CheckCircle className="h-3.5 w-3.5 text-emerald-300" />
                    )}
                    <span className="text-xs font-semibold text-text-primary/95">
                      {milestone.title}
                    </span>
                  </div>
                  <span className="text-[10px] font-medium text-text-secondary/70">
                    {milestone.count} {milestone.count === 1 ? "event" : "events"}
                  </span>
                </div>
                <div className="mt-1 text-[11px] text-text-secondary/85">{milestone.detail}</div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="relative space-y-4 before:absolute before:inset-0 before:ml-2.5 before:h-full before:w-0.5 before:-translate-x-px before:bg-gradient-to-b before:from-border-subtle/50 before:via-border-subtle/20 before:to-transparent">
          <AnimatePresence mode="popLayout">
            {traceSteps.map((step, index) => (
              <motion.div
                key={`${step.tool_id}-${step.step_number}`}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.2, delay: index * 0.03 }}
                className="relative flex items-start gap-4 pl-0.5"
              >
                <div className="relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-bg-primary">
                  {step.status === "running" ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-accent-primary" aria-label="Running" />
                  ) : step.status === "error" ? (
                    <AlertTriangle className="h-3.5 w-3.5 text-red-400" aria-label="Error" />
                  ) : (
                    <CheckCircle className="h-3.5 w-3.5 text-emerald-400" aria-label="Completed" />
                  )}
                </div>

                <div className="flex min-w-0 flex-1 flex-col gap-1.5 pt-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-text-primary/90">{step.tool_name}</span>
                    <span className="rounded border border-border-subtle/30 bg-bg-secondary/50 px-1.5 py-0.5 text-[10px] font-medium text-text-secondary/50">
                      Step {step.step_number}
                    </span>
                  </div>

                  <div className="break-words text-xs leading-relaxed text-text-secondary/80">
                    <span className="mr-1 font-medium text-text-secondary/60">Action:</span>
                    {step.input}
                  </div>

                  {step.output && step.status === "completed" && (
                    <motion.details
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="mt-1 rounded-lg border border-border-subtle/20 bg-bg-secondary/30 p-2"
                    >
                      <summary className="cursor-pointer text-[11px] font-medium uppercase tracking-tight text-text-secondary/60">
                        Result (view raw)
                      </summary>
                      <div className="mt-2 max-h-64 overflow-y-auto scrollbar-thin text-[11px] font-mono text-text-secondary/90">
                        {step.output}
                      </div>
                    </motion.details>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
};
