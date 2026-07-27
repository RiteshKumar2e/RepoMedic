"use client";

import { useState } from "react";
import { AlertCircle, Github, Loader2, RefreshCw } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { useSyncRepositories } from "@/hooks/useRepositories";
import { Button } from "@/components/ui/Button";
import { startGitHubOAuth } from "@/lib/auth";
import { APIError } from "@/lib/api";

/**
 * The single entry point for getting repositories into the workspace.
 *
 * Three states, because the honest action differs:
 *  - demo account      → cannot sync at all, say so rather than failing on click
 *  - no GitHub linked  → send the user through OAuth first
 *  - GitHub linked     → import/refresh the repository list
 */
export function ConnectRepositories({ size = "default" }: { size?: "default" | "sm" }) {
  const { isDemo, githubConnected } = useAuth();
  const sync = useSyncRepositories();
  const [error, setError] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);

  const handleConnect = async () => {
    setError(null);
    setConnecting(true);
    try {
      const res = await startGitHubOAuth("/repositories");
      if (res.configured && res.authorize_url) {
        window.location.href = res.authorize_url;
        return;
      }
      setError("GitHub is not configured on this deployment, so repositories cannot be imported.");
    } catch {
      setError("Could not start the GitHub flow. Please try again.");
    } finally {
      setConnecting(false);
    }
  };

  const handleSync = async () => {
    setError(null);
    try {
      await sync.mutateAsync();
    } catch (err) {
      setError(err instanceof APIError ? err.message : "Could not reach the server.");
    }
  };

  if (isDemo) {
    return (
      <p className="flex items-start gap-1.5 text-[12px] text-ink-muted">
        <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-medium" />
        The demo workspace holds no GitHub credential. Sign in with GitHub to connect your own
        repositories.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {githubConnected ? (
        <Button size={size} onClick={handleSync} disabled={sync.isPending} className="gap-1.5">
          {sync.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          {sync.isPending ? "Importing from GitHub…" : "Sync repositories"}
        </Button>
      ) : (
        <Button
          size={size}
          variant="default"
          onClick={handleConnect}
          disabled={connecting}
          className="gap-1.5"
        >
          {connecting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Github className="h-4 w-4" />}
          {connecting ? "Redirecting to GitHub…" : "Connect GitHub"}
        </Button>
      )}

      {sync.isSuccess && !error && (
        <p className="text-[12px] text-success">
          Imported {sync.data?.length ?? 0}{" "}
          {sync.data?.length === 1 ? "repository" : "repositories"} from GitHub.
        </p>
      )}

      {error && (
        <p className="flex items-start gap-1.5 text-[12px] text-critical">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {error}
        </p>
      )}
    </div>
  );
}
