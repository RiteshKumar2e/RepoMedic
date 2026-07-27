"use client";

import { FolderGit2 } from "lucide-react";
import type { Repository } from "@/types/api";
import { cn } from "@/lib/utils";

/**
 * Picks which connected repository a page is showing.
 *
 * A native <select> on purpose: it is keyboard accessible and behaves correctly
 * on touch devices without a custom listbox implementation.
 */
export function RepositorySelect({
  repositories,
  value,
  onChange,
  isLoading,
  className,
}: {
  repositories: Repository[];
  value: string | null;
  onChange: (repositoryId: string) => void;
  isLoading?: boolean;
  className?: string;
}) {
  if (isLoading) {
    return <span className={cn("text-xs text-ink-subtle", className)}>Loading repositories…</span>;
  }

  if (repositories.length === 0) {
    return (
      <span className={cn("text-xs text-ink-subtle", className)}>No repositories connected</span>
    );
  }

  return (
    <label className={cn("flex items-center gap-2", className)}>
      <span className="sr-only">Repository</span>
      <FolderGit2 className="h-4 w-4 shrink-0 text-ink-subtle" />
      <select
        value={value ?? ""}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 max-w-[18rem] rounded-md border border-line bg-canvas px-2 text-[13px] text-ink transition-colors hover:border-ink-subtle focus:border-accent"
      >
        {repositories.map((repository) => (
          <option key={repository.id} value={repository.id}>
            {repository.full_name}
          </option>
        ))}
      </select>
    </label>
  );
}
