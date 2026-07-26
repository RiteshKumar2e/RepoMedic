"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { KnowledgeGraphData } from "@/types/api";

export function useRepositoryGraph(repositoryId: string, analysisId?: string) {
  const endpoint = analysisId
    ? `/repositories/${repositoryId}/graph?analysis_id=${analysisId}`
    : `/repositories/${repositoryId}/graph`;

  return useQuery({
    queryKey: ["graph", repositoryId, analysisId],
    queryFn: () => api.get<KnowledgeGraphData>(endpoint),
    enabled: !!repositoryId,
  });
}
