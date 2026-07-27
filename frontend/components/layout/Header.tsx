"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronDown, Github, LogOut, Settings, Sparkles, User } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

/** Turns "/repositories/abc" into "Repositories" for the breadcrumb. */
function sectionLabel(pathname: string | null): string {
  const segment = pathname?.split("/").filter(Boolean)[0];
  if (!segment) return "Overview";
  return segment.replace(/-/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function Header() {
  const { user, isAuthenticated, isDemo, logout, isSigningOut } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Dismiss on outside click and on Escape — a menu that traps you is a bug.
  useEffect(() => {
    if (!menuOpen) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [menuOpen]);

  const handleSignOut = async () => {
    setMenuOpen(false);
    await logout();
    router.replace("/login");
  };

  const displayName = user?.name || user?.login || "Developer";

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-line bg-canvas px-6">
      <nav aria-label="Breadcrumb" className="flex items-center gap-2 text-[13px]">
        <span className="text-ink-muted">Workspace</span>
        <span className="text-ink-subtle">/</span>
        <span className="font-medium text-ink">{sectionLabel(pathname)}</span>
      </nav>

      <div className="flex items-center gap-2">
        {isDemo && (
          <span className="hidden items-center gap-1.5 rounded-md border border-medium-line bg-medium-soft px-2 py-1 text-[11px] font-medium text-medium sm:inline-flex">
            <Sparkles className="h-3 w-3" />
            Demo workspace
          </span>
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

        {!isAuthenticated ? (
          <Button size="sm" onClick={() => router.push("/login")}>
            Sign in
          </Button>
        ) : (
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => setMenuOpen((open) => !open)}
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              className={cn(
                "flex h-8 items-center gap-2 rounded-md border border-transparent px-1.5 text-[13px] text-ink transition-colors hover:bg-surface",
                menuOpen && "border-line bg-surface",
              )}
            >
              {user?.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={user.avatar_url}
                  alt=""
                  className="h-5 w-5 rounded-full border border-line"
                />
              ) : (
                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent-soft text-accent">
                  <User className="h-3 w-3" />
                </span>
              )}
              <span className="hidden max-w-[12rem] truncate sm:inline">{displayName}</span>
              <ChevronDown className="h-3.5 w-3.5 text-ink-subtle" />
            </button>

            {menuOpen && (
              <div
                role="menu"
                aria-label="Account"
                className="absolute right-0 top-full z-30 mt-1.5 w-60 overflow-hidden rounded-md border border-line bg-overlay shadow-[var(--shadow-md)]"
              >
                <div className="border-b border-line px-3 py-2.5">
                  <p className="truncate text-[13px] font-medium text-ink">{displayName}</p>
                  <p className="truncate text-[12px] text-ink-muted">
                    {user?.email || (isDemo ? "Seeded demo account" : "No email on file")}
                  </p>
                </div>

                <div className="p-1">
                  <Link
                    href="/settings"
                    role="menuitem"
                    onClick={() => setMenuOpen(false)}
                    className="flex items-center gap-2 rounded-md px-2 py-1.5 text-[13px] text-ink-muted transition-colors hover:bg-surface hover:text-ink"
                  >
                    <Settings className="h-4 w-4 text-ink-subtle" />
                    Settings
                  </Link>

                  <button
                    type="button"
                    role="menuitem"
                    onClick={handleSignOut}
                    disabled={isSigningOut}
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[13px] text-ink-muted transition-colors hover:bg-critical-soft hover:text-critical disabled:opacity-55"
                  >
                    <LogOut className="h-4 w-4" />
                    {isSigningOut ? "Signing out…" : "Sign out"}
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
