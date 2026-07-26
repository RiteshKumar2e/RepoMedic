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
    <div className="h-12 px-4 border-b border-slate-800 bg-slate-950/60 flex items-center justify-between gap-4">
      {/* Search Input */}
      <div className="relative flex-1 max-w-xs">
        <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Filter by file or title..."
          className="w-full h-7 pl-8 pr-3 bg-slate-900 border border-slate-800 rounded text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-sky-500 font-mono"
        />
      </div>

      {/* Severity Toggles */}
      <div className="flex items-center space-x-1.5">
        <Filter className="w-3.5 h-3.5 text-slate-400 mr-1" />
        {severities.map((sev) => {
          const active = selectedSeverities.includes(sev);
          return (
            <button
              key={sev}
              onClick={() => onToggleSeverity(sev)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono capitalize transition-colors border ${
                active
                  ? "bg-slate-800 text-slate-200 border-slate-700 font-semibold"
                  : "bg-transparent text-slate-500 border-transparent hover:text-slate-300"
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
