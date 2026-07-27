"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  FolderGit2,
  GitFork,
  LayoutDashboard,
  Settings,
  Stethoscope,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
  { name: "Repositories", href: "/repositories", icon: FolderGit2 },
  { name: "Architecture", href: "/architecture", icon: GitFork },
  { name: "Analytics", href: "/analytics", icon: BarChart3 },
  { name: "Settings", href: "/settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 z-30 flex h-screen w-60 shrink-0 flex-col border-r border-line bg-surface">
      <div className="flex h-14 items-center gap-2.5 border-b border-line px-4">
        <Link href="/dashboard" className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-white">
            <Stethoscope className="h-4 w-4" strokeWidth={2.25} />
          </span>
          <span className="text-[15px] font-semibold tracking-tight text-ink">RepoMedic</span>
        </Link>
      </div>

      <nav className="flex-1 overflow-y-auto p-2">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href || pathname?.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.name}
              href={item.href}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-2.5 py-1.5 text-[13px] transition-colors",
                isActive
                  ? "bg-canvas font-semibold text-ink shadow-[inset_0_0_0_1px_var(--line)]"
                  : "font-medium text-ink-muted hover:bg-canvas hover:text-ink",
              )}
            >
              <Icon
                className={cn("h-4 w-4 shrink-0", isActive ? "text-accent" : "text-ink-subtle")}
                strokeWidth={2}
              />
              {item.name}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-line px-4 py-3">
        <p className="font-mono text-[11px] text-ink-subtle">v0.5.0</p>
      </div>
    </aside>
  );
}
