"use client";

import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import type { SSEProgressEvent } from "@/types/api";

interface AnalysisProgressProps {
  stage: string;
  progress: number;
  message?: string;
  liveEvent?: SSEProgressEvent | null;
}

export function AnalysisProgress({ stage, progress, message, liveEvent }: AnalysisProgressProps) {
  const isDone = progress >= 100 || stage === "done" || stage === "completed";

  return (
    <div className="px-4 py-2 border-b border-line bg-surface flex items-center justify-between gap-4 text-xs font-mono">
      <div className="flex items-center space-x-2.5 min-w-0">
        {!isDone ? (
          <Loader2 className="w-4 h-4 text-accent animate-spin shrink-0" />
        ) : (
          <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
        )}
        <span className="text-ink capitalize truncate">
          {liveEvent?.message || message || `Stage: ${stage}`}
        </span>
      </div>

      <div className="flex items-center space-x-3 shrink-0">
        <div className="w-32 bg-inset rounded-full h-1.5 overflow-hidden">
          <div
            className="bg-accent h-full transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-accent font-bold text-[11px]">{progress}%</span>
      </div>
    </div>
  );
}
