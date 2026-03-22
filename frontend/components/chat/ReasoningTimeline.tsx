"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CheckCircle, AlertTriangle, Loader2 } from "lucide-react";
import { ToolStatus } from "@/types";

interface ReasoningTimelineProps {
  steps: ToolStatus[];
}

export const ReasoningTimeline: React.FC<ReasoningTimelineProps> = ({ steps }) => {
  if (!steps || steps.length === 0) return null;

  return (
    <div className="flex flex-col gap-2 py-2">
      <div className="flex items-center gap-2 mb-2 px-1">
        <div className="h-px flex-1 bg-border-subtle/30" />
        <span className="text-[10px] font-bold uppercase tracking-widest text-text-secondary opacity-50">
          Reasoning Process
        </span>
        <div className="h-px flex-1 bg-border-subtle/30" />
      </div>
      
      <div className="relative space-y-4 before:absolute before:inset-0 before:ml-2.5 before:h-full before:w-0.5 before:-translate-x-px before:bg-gradient-to-b before:from-border-subtle/50 before:via-border-subtle/20 before:to-transparent">
        <AnimatePresence mode="popLayout">
          {steps.map((step, index) => (
            <motion.div
              key={`${step.tool_id}-${step.step_number}`}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, delay: index * 0.05 }}
              className="relative flex items-start gap-4 pl-0.5"
            >
              {/* Status Icon */}
              <div className="relative z-10 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-bg-primary">
                {step.status === "running" ? (
                  <Loader2 
                    className="h-3.5 w-3.5 animate-spin text-accent-primary" 
                    aria-label="Running"
                  />
                ) : step.status === "error" ? (
                  <AlertTriangle 
                    className="h-3.5 w-3.5 text-red-400" 
                    aria-label="Error"
                  />
                ) : (
                  <CheckCircle 
                    className="h-3.5 w-3.5 text-emerald-400" 
                    aria-label="Completed"
                  />
                )}
              </div>

              {/* Step Content */}
              <div className="flex flex-col gap-1.5 min-w-0 flex-1 pt-0.5">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-text-primary/90">
                    {step.tool_name}
                  </span>
                  <span className="text-[10px] font-medium text-text-secondary/50 px-1.5 py-0.5 rounded bg-bg-secondary/50 border border-border-subtle/30">
                    Step {step.step_number}
                  </span>
                </div>
                
                <div className="text-xs text-text-secondary/80 leading-relaxed break-words">
                  <span className="font-medium text-text-secondary/60 mr-1">Action:</span>
                  {step.input}
                </div>

                {step.output && step.status === "completed" && (
                  <motion.div 
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    className="mt-1 p-2 rounded-lg bg-bg-secondary/30 border border-border-subtle/20"
                  >
                    <div className="text-[11px] font-medium text-text-secondary/60 mb-1 uppercase tracking-tight">Result</div>
                    <div className="text-[11px] text-text-secondary/90 font-mono max-h-64 overflow-y-auto scrollbar-thin">
                      {step.output}
                    </div>
                  </motion.div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
};
