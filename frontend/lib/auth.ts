import { api, setAuthToken, clearAuthToken } from "./api";
import type { User } from "@/types/api";

export interface SessionResponse {
  authenticated: boolean;
  user: User | null;
}

export async function getCurrentSession(): Promise<SessionResponse> {
  try {
    return await api.get<SessionResponse>("/auth/session");
  } catch {
    return { authenticated: false, user: null };
  }
}

export async function loginAsDemoUser(): Promise<{ authenticated: boolean; user: User }> {
  const data = await api.post<{ authenticated: boolean; user: User; token?: string }>("/auth/demo");
  if (data.token) {
    setAuthToken(data.token);
  }
  return data;
}

export async function logoutUser(): Promise<{ success: boolean }> {
  clearAuthToken();
  return api.post<{ success: boolean }>("/auth/logout");
}
