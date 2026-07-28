"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getCurrentSession, loginWithPassword, logoutUser, registerUser } from "@/lib/auth";
import type { User } from "@/types/api";

const SESSION_KEY = ["auth-session"];

export function useAuth() {
  const queryClient = useQueryClient();

  const sessionQuery = useQuery({
    queryKey: SESSION_KEY,
    queryFn: getCurrentSession,
    staleTime: 1000 * 60 * 5, // 5 mins
    retry: false, // 401 is an answer, not a failure worth retrying
  });

  const onAuthenticated = (data: {
    user: User;
    github_connected?: boolean;
    is_admin?: boolean;
  }) => {
    queryClient.setQueryData(SESSION_KEY, {
      authenticated: true,
      user: data.user,
      // Carry these through, or the UI would think GitHub is unlinked and the
      // admin link would stay hidden until the session query refetches.
      github_connected: data.github_connected ?? false,
      is_admin: data.is_admin ?? false,
    });
    // Cached workspace data belongs to whoever was signed in before.
    queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] !== "auth-session" });
  };

  const registerMutation = useMutation({ mutationFn: registerUser, onSuccess: onAuthenticated });
  const loginMutation = useMutation({ mutationFn: loginWithPassword, onSuccess: onAuthenticated });

  const logoutMutation = useMutation({
    mutationFn: logoutUser,
    // onSettled, not onSuccess: a failed request still ends the local session.
    onSettled: () => {
      // Drop every cached workspace response so the next user starts clean,
      // then seed the signed-out session so guards resolve without a round trip.
      queryClient.clear();
      queryClient.setQueryData(SESSION_KEY, { authenticated: false, user: null });
    },
  });

  return {
    user: sessionQuery.data?.user ?? null,
    isAuthenticated: sessionQuery.data?.authenticated ?? false,
    isLoading: sessionQuery.isLoading,
    githubConnected: sessionQuery.data?.github_connected ?? false,
    isAdmin: sessionQuery.data?.is_admin ?? false,

    register: registerMutation.mutateAsync,
    isRegistering: registerMutation.isPending,

    login: loginMutation.mutateAsync,
    isSigningIn: loginMutation.isPending,

    logout: logoutMutation.mutateAsync,
    isSigningOut: logoutMutation.isPending,
  };
}
