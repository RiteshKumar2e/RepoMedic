import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import type { Severity, FindingCategory } from "@/types/api";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(dateStr?: string | null): string {
  if (!dateStr) return "N/A";
  const date = new Date(dateStr);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatDuration(seconds?: number | null): string {
  if (seconds === undefined || seconds === null) return "N/A";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

export function getSeverityBadgeColor(severity: Severity): {
  bg: string;
  text: string;
  border: string;
} {
  switch (severity) {
    case "critical":
      return { bg: "bg-red-500/10 dark:bg-red-950/40", text: "text-red-600 dark:text-red-400", border: "border-red-500/30" };
    case "high":
      return { bg: "bg-orange-500/10 dark:bg-orange-950/40", text: "text-orange-600 dark:text-orange-400", border: "border-orange-500/30" };
    case "medium":
      return { bg: "bg-amber-500/10 dark:bg-amber-950/40", text: "text-amber-600 dark:text-amber-400", border: "border-amber-500/30" };
    case "low":
      return { bg: "bg-blue-500/10 dark:bg-blue-950/40", text: "text-blue-600 dark:text-blue-400", border: "border-blue-500/30" };
    case "informational":
    default:
      return { bg: "bg-slate-500/10 dark:bg-slate-800/40", text: "text-slate-600 dark:text-slate-400", border: "border-slate-500/30" };
  }
}

export function getCategoryIcon(category: FindingCategory): string {
  switch (category) {
    case "security":
    case "secret":
    case "prompt_injection":
      return "ShieldAlert";
    case "bug":
      return "Bug";
    case "performance":
      return "Zap";
    case "architecture":
      return "GitFork";
    case "reliability":
      return "Activity";
    case "testing":
      return "TestTube";
    case "breaking_change":
      return "AlertTriangle";
    case "dependency":
      return "Package";
    case "code_quality":
    default:
      return "Code2";
  }
}
