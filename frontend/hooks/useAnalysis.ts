"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, subscribeToAnalysisEvents } from "@/lib/api";
import type { Analysis, SSEProgressEvent } from "@/types/api";

export function useAnalysis(analysisId: string) {
  const queryClient = useQueryClient();
  const [liveEvent, setLiveEvent] = useState<SSEProgressEvent | null>(null);

  const query = useQuery({
    queryKey: ["analyses", analysisId],
    queryFn: () => api.get<Analysis>(`/analyses/${analysisId}`),
    enabled: !!analysisId,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 3000 : false;
    },
  });

  useEffect(() => {
    if (!analysisId) return;

    const cleanup = subscribeToAnalysisEvents(analysisId, (event) => {
      setLiveEvent(event);
      if (event.type === "completed" || event.type === "failed" || event.type === "findings" || event.type === "patch") {
        queryClient.invalidateQueries({ queryKey: ["analyses", analysisId] });
        queryClient.invalidateQueries({ queryKey: ["findings", analysisId] });
      }
    });

    return cleanup;
  }, [analysisId, queryClient]);

  return {
    analysis: query.data ?? null,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    liveEvent,
  };
}
