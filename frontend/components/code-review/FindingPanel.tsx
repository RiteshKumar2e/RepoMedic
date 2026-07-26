"use client";

import { FindingCard } from "./FindingCard";
import type { Finding } from "@/types/api";

interface FindingPanelProps {
  findings: Finding[];
  onSelectFinding: (finding: Finding) => void;
  onApprovePatch?: (patchId: string) => void;
  onRejectPatch?: (patchId: string) => void;
  isApproving?: boolean;
  isRejecting?: boolean;
}

export function FindingPanel({
  findings,
  onSelectFinding,
  onApprovePatch,
  onRejectPatch,
  isApproving,
  isRejecting,
}: FindingPanelProps) {
  return (
    <div className="w-96 border-l border-line bg-canvas flex flex-col h-full overflow-hidden shrink-0">
      <div className="p-3 border-b border-line flex items-center justify-between">
        <span className="text-xs font-semibold text-ink uppercase tracking-wider">
          AI Findings & Fixes ({findings.length})
        </span>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {findings.length === 0 ? (
          <div className="p-6 text-center text-xs text-ink-subtle space-y-2">
            <p>No findings match the selected filters.</p>
          </div>
        ) : (
          findings.map((finding) => (
            <FindingCard
              key={finding.id}
              finding={finding}
              onSelectFinding={onSelectFinding}
              onApprovePatch={onApprovePatch}
              onRejectPatch={onRejectPatch}
              isApproving={isApproving}
              isRejecting={isRejecting}
            />
          ))
        )}
      </div>
    </div>
  );
}
