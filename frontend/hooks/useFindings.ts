"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Finding, Severity, FindingCategory, FindingSource, FindingStatus } from "@/types/api";

export interface FindingFilters {
  severity?: Severity[];
  category?: FindingCategory[];
  source?: FindingSource[];
  status?: FindingStatus[];
  filePath?: string;
  minConfidence?: number;
}

export function useFindings(analysisId: string, filters: FindingFilters = {}) {
  const params = new URLSearchParams();
  if (filters.severity?.length) filters.severity.forEach((s) => params.append("severity", s));
  if (filters.category?.length) filters.category.forEach((c) => params.append("category", c));
  if (filters.source?.length) filters.source.forEach((src) => params.append("source", src));
  if (filters.status?.length) filters.status.forEach((st) => params.append("status", st));
  if (filters.filePath) params.append("file_path", filters.filePath);
  if (filters.minConfidence !== undefined) params.append("min_confidence", filters.minConfidence.toString());

  const queryString = params.toString();
  const endpoint = `/analyses/${analysisId}/findings${queryString ? `?${queryString}` : ""}`;

  return useQuery({
    queryKey: ["findings", analysisId, filters],
    queryFn: () => api.get<Finding[]>(endpoint),
    enabled: !!analysisId,
  });
}

export function useGenerateFix(analysisId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (findingId: string) => api.post(`/findings/${findingId}/generate-fix`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["findings", analysisId] });
      queryClient.invalidateQueries({ queryKey: ["analyses", analysisId] });
    },
  });
}
