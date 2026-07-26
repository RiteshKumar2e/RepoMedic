"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Patch } from "@/types/api";

export function usePatchActions(analysisId?: string) {
  const queryClient = useQueryClient();

  const validateMutation = useMutation({
    mutationFn: (patchId: string) => api.post<Patch>(`/patches/${patchId}/validate`),
    onSuccess: () => {
      if (analysisId) {
        queryClient.invalidateQueries({ queryKey: ["findings", analysisId] });
        queryClient.invalidateQueries({ queryKey: ["analyses", analysisId] });
      }
    },
  });

  const approveMutation = useMutation({
    mutationFn: (patchId: string) => api.post<Patch>(`/patches/${patchId}/approve`),
    onSuccess: () => {
      if (analysisId) {
        queryClient.invalidateQueries({ queryKey: ["findings", analysisId] });
        queryClient.invalidateQueries({ queryKey: ["analyses", analysisId] });
      }
    },
  });

  const rejectMutation = useMutation({
    mutationFn: ({ patchId, reason }: { patchId: string; reason?: string }) =>
      api.post<Patch>(`/patches/${patchId}/reject`, { reason }),
    onSuccess: () => {
      if (analysisId) {
        queryClient.invalidateQueries({ queryKey: ["findings", analysisId] });
        queryClient.invalidateQueries({ queryKey: ["analyses", analysisId] });
      }
    },
  });

  const publishReviewMutation = useMutation({
    mutationFn: (id: string) => api.post(`/analyses/${id}/publish-review`),
  });

  const createFixPRMutation = useMutation({
    mutationFn: ({ id, branchName, title }: { id: string; branchName?: string; title?: string }) =>
      api.post(`/analyses/${id}/create-fix-pr`, { branch_name: branchName, title }),
  });

  return {
    validatePatch: validateMutation.mutateAsync,
    isValidating: validateMutation.isPending,
    approvePatch: approveMutation.mutateAsync,
    isApproving: approveMutation.isPending,
    rejectPatch: rejectMutation.mutateAsync,
    isRejecting: rejectMutation.isPending,
    publishReview: publishReviewMutation.mutateAsync,
    isPublishing: publishReviewMutation.isPending,
    createFixPR: createFixPRMutation.mutateAsync,
    isCreatingPR: createFixPRMutation.isPending,
  };
}
