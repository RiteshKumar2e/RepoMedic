"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { DashboardSummary, RepositoryAnalytics } from "@/types/api";

/**
 * The workspace dashboard and the per-repository report are different
 * endpoints returning different shapes, so they get separate hooks rather than
 * one hook with an optional argument and a single (wrong) return type.
 */
export function useAnalytics() {
  return useQuery({
    queryKey: ["analytics", "dashboard"],
    queryFn: () => api.get<DashboardSummary>("/dashboard"),
  });
}

export function useRepositoryAnalytics(repositoryId?: string) {
  return useQuery({
    queryKey: ["analytics", "repository", repositoryId],
    queryFn: () => api.get<RepositoryAnalytics>(`/repositories/${repositoryId}/analytics`),
    enabled: Boolean(repositoryId),
  });
}
