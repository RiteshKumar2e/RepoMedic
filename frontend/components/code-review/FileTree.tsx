"use client";

import { FileCode2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/Badge";
import type { Finding } from "@/types/api";

interface FileTreeProps {
  files: Array<{ path: string; status?: string }>;
  selectedFile: string | null;
  onSelectFile: (path: string) => void;
  findings: Finding[];
}

export function FileTree({ files, selectedFile, onSelectFile, findings }: FileTreeProps) {
  const getFindingCount = (path: string) => findings.filter((f) => f.file_path === path).length;
  const getHighestSeverity = (path: string) => {
    const fileFindings = findings.filter((f) => f.file_path === path);
    if (fileFindings.some((f) => f.severity === "critical")) return "critical";
    if (fileFindings.some((f) => f.severity === "high")) return "high";
    if (fileFindings.some((f) => f.severity === "medium")) return "medium";
    if (fileFindings.some((f) => f.severity === "low")) return "low";
    return null;
  };

  return (
    <div className="w-64 border-r border-line bg-canvas flex flex-col h-full overflow-hidden shrink-0">
      <div className="p-3 border-b border-line flex items-center justify-between text-xs font-semibold text-ink-muted uppercase tracking-wider">
        <span>Changed Files ({files.length})</span>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {files.map((file) => {
          const count = getFindingCount(file.path);
          const topSeverity = getHighestSeverity(file.path);
          const isSelected = selectedFile === file.path;

          return (
            <button
              key={file.path}
              onClick={() => onSelectFile(file.path)}
              className={cn(
                "w-full flex items-center justify-between px-2.5 py-2 rounded-md text-xs font-mono transition-colors text-left",
                isSelected
                  ? "bg-accent-soft text-accent border border-accent-line"
                  : "text-ink hover:bg-surface hover:text-ink"
              )}
            >
              <div className="flex items-center space-x-2 min-w-0 truncate">
                <FileCode2 className="w-3.5 h-3.5 shrink-0 text-ink-muted" />
                <span className="truncate">{file.path}</span>
              </div>

              {count > 0 && (
                <Badge
                  variant={topSeverity ?? "medium"}
                  className="px-1.5 py-0 text-[10px] h-4 font-mono shrink-0 ml-1"
                >
                  {count}
                </Badge>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
