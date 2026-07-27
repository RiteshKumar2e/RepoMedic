"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AlertCircle, Github, Loader2, Sparkles } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/Button";
import { Input, Label, FieldError } from "@/components/ui/Input";
import { startGitHubOAuth } from "@/lib/auth";
import { APIError } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { login, demoLogin, isSigningIn, isLoggingIn } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [gitHubState, setGitHubState] = useState<"idle" | "redirecting" | "unavailable">("idle");

  // Set by RequireAuth when it bounces an unauthenticated visit.
  const nextPath = searchParams.get("next") || "/dashboard";

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await login({ email, password });
      router.replace(nextPath);
    } catch (err) {
      setError(
        err instanceof APIError ? err.message : "Could not reach the server. Please try again.",
      );
    }
  };

  const handleGitHub = async () => {
    setError(null);
    setGitHubState("redirecting");
    try {
      const res = await startGitHubOAuth(nextPath);
      if (res.configured && res.authorize_url) {
        window.location.href = res.authorize_url;
        return;
      }
      // Honest failure: this deployment has no GitHub credentials configured.
      setGitHubState("unavailable");
    } catch {
      setGitHubState("unavailable");
    }
  };

  const handleDemo = async () => {
    setError(null);
    try {
      await demoLogin();
      router.replace("/dashboard");
    } catch {
      setError("Demo mode is disabled on this deployment.");
    }
  };

  const busy = isSigningIn || isLoggingIn || gitHubState === "redirecting";

  return (
    <AuthShell
      title="Sign in to RepoMedic"
      subtitle="Review, validate and ship fixes with your whole repository in context."
      footer={
        <span>
          New to RepoMedic?{" "}
          <Link href="/register" className="font-medium text-accent hover:underline">
            Create an account
          </Link>
        </span>
      }
    >
      <div className="space-y-5">
        <Button
          type="button"
          onClick={handleGitHub}
          disabled={busy}
          className="h-9 w-full gap-2"
          variant="secondary"
        >
          {gitHubState === "redirecting" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Github className="h-4 w-4" />
          )}
          {gitHubState === "redirecting" ? "Redirecting to GitHub…" : "Continue with GitHub"}
        </Button>

        {gitHubState === "unavailable" && (
          <p className="flex gap-1.5 text-[12px] text-ink-muted">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-medium" />
            GitHub sign-in is not configured on this deployment. Use an email account or the demo
            workspace below.
          </p>
        )}

        <div className="relative text-center">
          <span className="absolute inset-x-0 top-1/2 border-t border-line" aria-hidden />
          <span className="relative bg-canvas px-3 font-mono text-[11px] uppercase tracking-wider text-ink-subtle">
            or
          </span>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={Boolean(error)}
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between">
              <Label htmlFor="password">Password</Label>
            </div>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              placeholder="••••••••••"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "login-error" : undefined}
            />
          </div>

          {error && (
            <div
              id="login-error"
              role="alert"
              className="flex items-start gap-2 rounded-md border border-critical-line bg-critical-soft px-3 py-2"
            >
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" />
              <FieldError>{error}</FieldError>
            </div>
          )}

          <Button type="submit" variant="default" disabled={busy} className="h-9 w-full">
            {isSigningIn && <Loader2 className="h-4 w-4 animate-spin" />}
            {isSigningIn ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <div className="rounded-md border border-line bg-surface px-3 py-3">
          <p className="text-[12px] text-ink-muted">
            Want to look around first? The demo workspace is seeded from a local fixture repository
            — no GitHub access, no writes.
          </p>
          <Button
            type="button"
            onClick={handleDemo}
            disabled={busy}
            variant="ghost"
            size="sm"
            className="mt-2 gap-1.5 px-0 hover:bg-transparent hover:text-accent"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {isLoggingIn ? "Preparing demo…" : "Explore the demo workspace"}
          </Button>
        </div>
      </div>
    </AuthShell>
  );
}

export default function LoginPage() {
  // useSearchParams needs a Suspense boundary for static rendering.
  return (
    <Suspense fallback={<div className="min-h-screen bg-canvas" />}>
      <LoginForm />
    </Suspense>
  );
}
