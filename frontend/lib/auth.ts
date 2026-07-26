import { api } from "./api";
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
  return api.post<{ authenticated: boolean; user: User }>("/auth/demo");
}

export async function logoutUser(): Promise<{ success: boolean }> {
  return api.post<{ success: boolean }>("/auth/logout");
}
