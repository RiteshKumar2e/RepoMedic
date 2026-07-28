import { api, setAuthToken, clearAuthToken } from "./api";
import type { User } from "@/types/api";

export interface SessionResponse {
  authenticated: boolean;
  user: User | null;
  github_connected?: boolean;
}

interface AuthenticatedResponse {
  authenticated: boolean;
  user: User;
  github_connected?: boolean;
  token?: string;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

/**
 * The session cookie is httpOnly, so the bearer token returned alongside it is
 * what survives a page that talks to the API from a different origin.
 */
function persistSession(data: AuthenticatedResponse): AuthenticatedResponse {
  if (data.token) setAuthToken(data.token);
  return data;
}

/**
 * Pick up a session handed back by the GitHub OAuth redirect.
 *
 * The backend appends `#session=<token>` when the app and the API are on
 * different sites, because there the session cookie is a third-party cookie and
 * browsers may block it entirely. Storing the token means later requests
 * authenticate with an `Authorization` header, which nothing blocks.
 *
 * The fragment is removed from the address bar immediately so the token is not
 * left sitting in a URL the user might copy or bookmark.
 */
export function consumeSessionFromUrl(): boolean {
  if (typeof window === "undefined") return false;

  const hash = window.location.hash;
  if (!hash.startsWith("#")) return false;

  const token = new URLSearchParams(hash.slice(1)).get("session");
  if (!token) return false;

  setAuthToken(token);
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  return true;
}

export async function getCurrentSession(): Promise<SessionResponse> {
  try {
    return await api.get<SessionResponse>("/auth/session");
  } catch {
    return { authenticated: false, user: null };
  }
}

export async function registerUser(payload: RegisterPayload): Promise<AuthenticatedResponse> {
  return persistSession(await api.post<AuthenticatedResponse>("/auth/register", payload));
}

export async function loginWithPassword(payload: LoginPayload): Promise<AuthenticatedResponse> {
  return persistSession(await api.post<AuthenticatedResponse>("/auth/login", payload));
}

export async function startGitHubOAuth(redirectPath = "/dashboard") {
  return api.post<{ authorize_url: string; state: string; configured: boolean }>("/auth/github", {
    redirect_path: redirectPath,
  });
}

export async function logoutUser(): Promise<{ success: boolean }> {
  try {
    return await api.post<{ success: boolean }>("/auth/logout");
  } finally {
    // Clear locally even if the server call fails — the user asked to leave.
    clearAuthToken();
  }
}
