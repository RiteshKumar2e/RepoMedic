"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AnalyticsSummary } from "@/types/api";

export function useAnalytics(repositoryId?: string) {
  const endpoint = repositoryId ? `/repositories/${repositoryId}/analytics` : `/dashboard`;

  return useQuery({
    queryKey: ["analytics", repositoryId],
    queryFn: () => api.get<AnalyticsSummary>(endpoint),
  });
}
