"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getCurrentSession, loginAsDemoUser, logoutUser } from "@/lib/auth";
import type { User } from "@/types/api";

export function useAuth() {
  const queryClient = useQueryClient();

  const sessionQuery = useQuery({
    queryKey: ["auth-session"],
    queryFn: getCurrentSession,
    staleTime: 1000 * 60 * 5, // 5 mins
  });

  const demoLoginMutation = useMutation({
    mutationFn: loginAsDemoUser,
    onSuccess: (data) => {
      queryClient.setQueryData(["auth-session"], {
        authenticated: true,
        user: data.user,
      });
      queryClient.invalidateQueries();
    },
  });

  const logoutMutation = useMutation({
    mutationFn: logoutUser,
    onSuccess: () => {
      queryClient.setQueryData(["auth-session"], {
        authenticated: false,
        user: null,
      });
      queryClient.invalidateQueries();
    },
  });

  return {
    user: sessionQuery.data?.user ?? null,
    isAuthenticated: sessionQuery.data?.authenticated ?? false,
    isLoading: sessionQuery.isLoading,
    isDemo: sessionQuery.data?.user?.is_demo ?? false,
    demoLogin: demoLoginMutation.mutateAsync,
    isLoggingIn: demoLoginMutation.isPending,
    logout: logoutMutation.mutateAsync,
  };
}
