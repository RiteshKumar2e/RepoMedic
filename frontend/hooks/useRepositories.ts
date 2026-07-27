"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Repository, RepositorySettings } from "@/types/api";

export function useRepositories() {
  return useQuery({
    queryKey: ["repositories"],
    queryFn: () => api.get<Repository[]>("/repositories"),
  });
}

/**
 * Import repositories from GitHub. This is the "connect a repository" action:
 * the backend pulls everything the installation can see and upserts it.
 * Rejected for demo accounts, which hold no GitHub credential.
 */
export function useSyncRepositories() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => api.post<Repository[]>("/repositories/sync"),
    onSuccess: (repositories) => {
      queryClient.setQueryData(["repositories"], repositories);
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
}

export function useRepository(repositoryId: string) {
  return useQuery({
    queryKey: ["repositories", repositoryId],
    queryFn: () => api.get<Repository>(`/repositories/${repositoryId}`),
    enabled: !!repositoryId,
  });
}

export function useUpdateRepositorySettings(repositoryId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (settings: Partial<RepositorySettings>) =>
      api.put<RepositorySettings>(`/repositories/${repositoryId}/settings`, settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["repositories", repositoryId] });
    },
  });
}
