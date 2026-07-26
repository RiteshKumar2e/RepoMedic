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
