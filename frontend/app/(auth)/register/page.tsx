"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertCircle, Check, Github, Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { AuthShell } from "@/components/auth/AuthShell";
import { Button } from "@/components/ui/Button";
import { Input, Label, FieldError } from "@/components/ui/Input";
import { startGitHubOAuth } from "@/lib/auth";
import { APIError } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Mirrors the server-side policy in backend/app/schemas/auth.py. */
const RULES = [
  { label: "At least 10 characters", test: (v: string) => v.length >= 10 },
  { label: "Contains a letter", test: (v: string) => /[a-zA-Z]/.test(v) },
  { label: "Contains a number", test: (v: string) => /\d/.test(v) },
];

export default function RegisterPage() {
  const router = useRouter();
  const { register, isRegistering } = useAuth();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [gitHubBusy, setGitHubBusy] = useState(false);

  const results = useMemo(() => RULES.map((rule) => rule.test(password)), [password]);
  const passwordValid = results.every(Boolean);
  const canSubmit = name.trim() !== "" && email.trim() !== "" && passwordValid && !isRegistering;

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await register({ name: name.trim(), email: email.trim(), password });
      router.replace("/dashboard");
    } catch (err) {
      setError(
        err instanceof APIError ? err.message : "Could not reach the server. Please try again.",
      );
    }
  };

  const handleGitHub = async () => {
    setError(null);
    setGitHubBusy(true);
    try {
      const res = await startGitHubOAuth("/dashboard");
      if (res.configured && res.authorize_url) {
        window.location.href = res.authorize_url;
        return;
      }
      setError("GitHub sign-up is not configured on this deployment. Use an email account below.");
    } catch {
      setError("GitHub sign-up is unavailable right now. Use an email account below.");
    } finally {
      setGitHubBusy(false);
    }
  };

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start reviewing repositories in a few minutes. No credit card required."
      footer={
        <span>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-accent hover:underline">
            Sign in
          </Link>
        </span>
      }
    >
      <div className="space-y-5">
        <Button
          type="button"
          onClick={handleGitHub}
          disabled={gitHubBusy || isRegistering}
          className="h-9 w-full gap-2"
          variant="secondary"
        >
          {gitHubBusy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Github className="h-4 w-4" />
          )}
          {gitHubBusy ? "Redirecting to GitHub…" : "Sign up with GitHub"}
        </Button>

        <div className="relative text-center">
          <span className="absolute inset-x-0 top-1/2 border-t border-line" aria-hidden />
          <span className="relative bg-canvas px-3 font-mono text-[11px] uppercase tracking-wider text-ink-subtle">
            or
          </span>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="name">Full name</Label>
            <Input
              id="name"
              name="name"
              autoComplete="name"
              placeholder="Ada Lovelace"
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="email">Work email</Label>
            <Input
              id="email"
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              placeholder="At least 10 characters"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby="password-rules"
            />
            <ul id="password-rules" className="space-y-1 pt-1">
              {RULES.map((rule, index) => {
                const met = results[index];
                return (
                  <li
                    key={rule.label}
                    className={cn(
                      "flex items-center gap-1.5 text-[12px]",
                      met ? "text-success" : "text-ink-subtle",
                    )}
                  >
                    <Check
                      className={cn("h-3 w-3", met ? "opacity-100" : "opacity-35")}
                      strokeWidth={3}
                    />
                    {rule.label}
                  </li>
                );
              })}
            </ul>
          </div>

          {error && (
            <div
              role="alert"
              className="flex items-start gap-2 rounded-md border border-critical-line bg-critical-soft px-3 py-2"
            >
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-critical" />
              <FieldError>{error}</FieldError>
            </div>
          )}

          <Button type="submit" variant="default" disabled={!canSubmit} className="h-9 w-full">
            {isRegistering && <Loader2 className="h-4 w-4 animate-spin" />}
            {isRegistering ? "Creating account…" : "Create account"}
          </Button>
        </form>

        <p className="text-[12px] leading-relaxed text-ink-subtle">
          RepoMedic requests read-only code access. Secrets are redacted before analysis, and every
          review action is written to an audit log.
        </p>
      </div>
    </AuthShell>
  );
}
