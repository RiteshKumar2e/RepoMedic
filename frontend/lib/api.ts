import type { JsonObject, SSEProgressEvent } from "@/types/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

const TOKEN_KEY = "repomedic_token";

export function setAuthToken(token: string) {
  if (typeof window !== "undefined") localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken() {
  if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);
}

export function getAuthToken(): string | null {
  if (typeof window !== "undefined") return localStorage.getItem(TOKEN_KEY);
  return null;
}

/** The envelope every backend error handler in app/main.py produces. */
interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: JsonObject;
  };
}

export class APIError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: JsonObject,
  ) {
    super(message);
    this.name = "APIError";
  }
}

async function fetcher<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint.startsWith("/") ? endpoint : `/${endpoint}`}`;
  
  const headers = new Headers(options.headers || {});
  if (!headers.has("Content-Type") && options.body && typeof options.body === "string") {
    headers.set("Content-Type", "application/json");
  }

  const token = getAuthToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!res.ok) {
    let errorPayload: ErrorEnvelope = {};
    try {
      errorPayload = (await res.json()) as ErrorEnvelope;
    } catch {
      // Not JSON
    }
    const code = errorPayload?.error?.code || "unknown_error";
    const message = errorPayload?.error?.message || res.statusText || "Request failed";
    throw new APIError(res.status, code, message, errorPayload?.error?.details);
  }

  if (res.status === 204) {
    return {} as T;
  }

  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(endpoint: string, options?: RequestInit) => fetcher<T>(endpoint, { ...options, method: "GET" }),
  post: <T>(endpoint: string, body?: unknown, options?: RequestInit) =>
    fetcher<T>(endpoint, {
      ...options,
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }),
  put: <T>(endpoint: string, body?: unknown, options?: RequestInit) =>
    fetcher<T>(endpoint, {
      ...options,
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(endpoint: string, options?: RequestInit) => fetcher<T>(endpoint, { ...options, method: "DELETE" }),
};

export function subscribeToAnalysisEvents(
  analysisId: string,
  onEvent: (event: SSEProgressEvent) => void,
  onError?: (err: Event) => void
): () => void {
  // EventSource cannot set an Authorization header, so the session cookie is
  // the only credential available — and cross-origin it is only sent with
  // withCredentials. Without this the stream 401s.
  const url = `${API_BASE}/analyses/${analysisId}/events`;
  const eventSource = new EventSource(url, { withCredentials: true });

  eventSource.onmessage = (e) => {
    try {
      const data: SSEProgressEvent = JSON.parse(e.data);
      onEvent(data);
      if (data.type === "completed" || data.type === "failed") {
        eventSource.close();
      }
    } catch (err) {
      console.error("Failed to parse SSE event payload", err);
    }
  };

  eventSource.onerror = (e) => {
    if (onError) onError(e);
    // Don't auto-close immediately; allow retry or component unmount to handle
  };

  return () => {
    eventSource.close();
  };
}
