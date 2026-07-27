"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

/**
 * Gates a workspace page behind a session.
 *
 * Unauthenticated visits are sent to /login carrying the path they wanted, so
 * signing in lands them where they were headed rather than on the dashboard.
 */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const next = pathname && pathname !== "/dashboard" ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/login${next}`);
    }
  }, [isAuthenticated, isLoading, pathname, router]);

  if (isLoading || !isAuthenticated) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas" aria-busy="true">
        <span className="flex items-center gap-2 text-[13px] text-ink-muted">
          <Loader2 className="h-4 w-4 animate-spin" />
          {isLoading ? "Checking your session…" : "Redirecting to sign in…"}
        </span>
      </div>
    );
  }

  return <>{children}</>;
}
