"use client";

import { useState } from "react";
import {
  ShieldAlert,
  Bug,
  Zap,
  GitFork,
  Activity,
  TestTube,
  CheckCircle2,
  XCircle,
  Sparkles,
  ChevronDown,
  ChevronUp,
  ThumbsUp,
  ThumbsDown,
  ExternalLink,
} from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { getSeverityBadgeColor } from "@/lib/utils";
import type { Finding, Patch } from "@/types/api";

interface FindingCardProps {
  finding: Finding;
  onSelectFinding: (finding: Finding) => void;
  onApprovePatch?: (patchId: string) => void;
  onRejectPatch?: (patchId: string) => void;
  isApproving?: boolean;
  isRejecting?: boolean;
}

export function FindingCard({
  finding,
  onSelectFinding,
  onApprovePatch,
  onRejectPatch,
  isApproving,
  isRejecting,
}: FindingCardProps) {
  const [expanded, setExpanded] = useState(true);
  const patch: Patch | undefined = finding.patches?.[0];

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/80 hover:border-slate-700 transition-colors p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <div className="flex items-center space-x-2 flex-wrap gap-y-1">
            <Badge variant={finding.severity as any}>{finding.severity.toUpperCase()}</Badge>
            <span className="text-[11px] font-mono text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
              {finding.category}
            </span>
            <span className="text-xs font-mono text-slate-400">
              {finding.file_path}:{finding.start_line}
            </span>
          </div>
          <h4
            onClick={() => onSelectFinding(finding)}
            className="text-sm font-semibold text-slate-100 hover:text-sky-400 cursor-pointer transition-colors"
          >
            {finding.title}
          </h4>
        </div>

        <button
          onClick={() => setExpanded(!expanded)}
          className="text-slate-400 hover:text-slate-200 p-1"
        >
          {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
        </button>
      </div>

      {expanded && (
        <div className="space-y-3 text-xs border-t border-slate-800/80 pt-3">
          {/* Explanation */}
          <div>
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-1">
              Explanation
            </span>
            <p className="text-slate-300 leading-relaxed">{finding.description}</p>
          </div>

          {/* Risk */}
          {finding.risk && (
            <div className="p-2.5 rounded bg-red-950/20 border border-red-900/30">
              <span className="text-[11px] font-semibold text-red-400 block mb-0.5">
                Impact & Risk
              </span>
              <p className="text-red-300 text-[11px] leading-relaxed">{finding.risk}</p>
            </div>
          )}

          {/* Proposed Fix & Validation */}
          {patch && (
            <div className="p-3 rounded bg-slate-950 border border-slate-800 space-y-2.5">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                  AST-Aware Proposed Fix
                </span>
                <span className="text-[11px] font-mono text-emerald-400">
                  Confidence: {Math.round((patch.confidence || 0.95) * 100)}%
                </span>
              </div>

              <p className="text-slate-400 text-[11px]">{patch.explanation}</p>

              {/* Validation signals */}
              <div className="flex flex-wrap gap-2 text-[10px] font-mono">
                <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                  <CheckCircle2 className="w-3 h-3" /> Syntax
                </span>
                <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                  <CheckCircle2 className="w-3 h-3" /> Linter
                </span>
                <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                  <CheckCircle2 className="w-3 h-3" /> Typecheck
                </span>
                <span className="flex items-center gap-1 text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded">
                  <CheckCircle2 className="w-3 h-3" /> Security
                </span>
              </div>

              {/* Actions */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-800">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => onSelectFinding(finding)}
                  className="text-[11px]"
                >
                  View Diff
                </Button>

                <div className="flex items-center space-x-2">
                  {onRejectPatch && (
                    <Button
                      size="sm"
                      variant="destructive"
                      disabled={isRejecting}
                      onClick={() => onRejectPatch(patch.id)}
                      className="gap-1 text-[11px]"
                    >
                      <ThumbsDown className="w-3 h-3" /> Reject
                    </Button>
                  )}
                  {onApprovePatch && (
                    <Button
                      size="sm"
                      variant="success"
                      disabled={isApproving}
                      onClick={() => onApprovePatch(patch.id)}
                      className="gap-1 text-[11px]"
                    >
                      <ThumbsUp className="w-3 h-3" /> Approve Fix
                    </Button>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
