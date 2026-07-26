"use client";

import { useRouter } from "next/navigation";
import { Github, LogOut, User } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";

export function Header() {
  const { user, isAuthenticated, isDemo, demoLogin, logout, isLoggingIn } = useAuth();
  const router = useRouter();

  const handleDemoClick = async () => {
    await demoLogin();
    router.push("/dashboard");
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-line bg-canvas px-6">
      <div className="flex items-center gap-2 text-[13px]">
        <span className="text-ink-muted">Workspace</span>
        {isDemo && (
          <>
            <span className="text-ink-subtle">/</span>
            <span className="font-medium text-ink">Demo</span>
          </>
        )}
      </div>

      <div className="flex items-center gap-2">
        {!isAuthenticated && (
          <Button onClick={handleDemoClick} disabled={isLoggingIn} size="sm">
            {isLoggingIn ? "Loading…" : "Explore demo"}
          </Button>
        )}

        {isAuthenticated && user && (
          <>
            <span className="flex items-center gap-2 text-[13px] text-ink">
              {user.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={user.avatar_url}
                  alt=""
                  className="h-5 w-5 rounded-full border border-line"
                />
              ) : (
                <User className="h-4 w-4 text-ink-subtle" />
              )}
              {user.login || user.name || "Developer"}
            </span>
            <Button variant="ghost" size="icon" onClick={() => logout()} title="Sign out">
              <LogOut className="h-4 w-4" />
              <span className="sr-only">Sign out</span>
            </Button>
          </>
        )}

        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          title="GitHub"
          className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-muted transition-colors hover:bg-surface hover:text-ink"
        >
          <Github className="h-4 w-4" />
          <span className="sr-only">GitHub</span>
        </a>
      </div>
    </header>
  );
}
