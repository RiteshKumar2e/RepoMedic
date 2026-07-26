"use client";

import { Search, Filter, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/Badge";
import type { Severity } from "@/types/api";

interface FilterBarProps {
  selectedSeverities: Severity[];
  onToggleSeverity: (severity: Severity) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  totalCount: number;
}

export function FilterBar({
  selectedSeverities,
  onToggleSeverity,
  searchQuery,
  onSearchChange,
  totalCount,
}: FilterBarProps) {
  const severities: Severity[] = ["critical", "high", "medium", "low", "informational"];

  return (
    <div className="h-12 px-4 border-b border-line bg-canvas flex items-center justify-between gap-4">
      {/* Search Input */}
      <div className="relative flex-1 max-w-xs">
        <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-muted" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter by file or title..."
          className="w-full h-7 pl-8 pr-3 bg-surface border border-line rounded text-xs text-ink placeholder:text-ink-subtle focus:outline-none focus:border-accent-line font-mono"
        />
      </div>

      {/* Severity Toggles */}
      <div className="flex items-center space-x-1.5">
        <Filter className="w-3.5 h-3.5 text-ink-muted mr-1" />
        {severities.map((sev) => {
          const active = selectedSeverities.includes(sev);
          return (
            <button
              key={sev}
              onClick={() => onToggleSeverity(sev)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono capitalize transition-colors border ${
                active
                  ? "bg-inset text-ink border-line font-semibold"
                  : "bg-transparent text-ink-subtle border-transparent hover:text-ink"
              }`}
            >
              {sev}
            </button>
          );
        })}
      </div>
    </div>
  );
}
