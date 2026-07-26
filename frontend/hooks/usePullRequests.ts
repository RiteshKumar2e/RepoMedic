"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { PullRequest, Analysis } from "@/types/api";

export function usePullRequests(repositoryId: string) {
  return useQuery({
    queryKey: ["repositories", repositoryId, "pull-requests"],
    queryFn: () => api.get<PullRequest[]>(`/repositories/${repositoryId}/pull-requests`),
    enabled: !!repositoryId,
  });
}

export function usePullRequest(pullRequestId: string) {
  return useQuery({
    queryKey: ["pull-requests", pullRequestId],
    queryFn: () => api.get<PullRequest>(`/pull-requests/${pullRequestId}`),
    enabled: !!pullRequestId,
  });
}

export function useTriggerAnalysis(pullRequestId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (options?: { force?: boolean; reviewers?: string[]; generate_patches?: boolean }) =>
      api.post<Analysis>(`/pull-requests/${pullRequestId}/analyze`, options || {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pull-requests", pullRequestId] });
      queryClient.invalidateQueries({ queryKey: ["analyses"] });
    },
  });
}
