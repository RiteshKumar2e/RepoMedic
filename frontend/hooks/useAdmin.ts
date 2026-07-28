"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import type { AdminOverview } from "@/types/api";

/**
 * System-wide view across every account.
 *
 * Only fetched when the session says the caller is an admin — the API enforces
 * this too, so this just avoids a guaranteed 403 on every other page load.
 */
export function useAdminOverview(limit = 50) {
  const { isAdmin } = useAuth();

  return useQuery({
    queryKey: ["admin", "overview", limit],
    queryFn: () => api.get<AdminOverview>(`/admin/overview?limit=${limit}`),
    enabled: isAdmin,
  });
}
