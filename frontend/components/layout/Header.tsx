"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { User, LogOut, Github, Sparkles, ExternalLink } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";

export function Header() {
  const { user, isAuthenticated, isDemo, demoLogin, logout, isLoggingIn } = useAuth();
  const router = useRouter();

  const handleDemoClick = async () => {
    await demoLogin();
    router.push("/dashboard");
  };

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/60 backdrop-blur-md px-6 flex items-center justify-between sticky top-0 z-20">
      <div className="flex items-center space-x-3 text-sm">
        <span className="text-slate-400 font-mono text-xs">RepoMedic</span>
        <span className="text-slate-600">/</span>
        <span className="text-slate-200 font-medium text-xs">Workspace</span>
      </div>

      <div className="flex items-center space-x-4">
        {!isAuthenticated && (
          <button
            onClick={handleDemoClick}
            disabled={isLoggingIn}
            className="px-3 py-1.5 text-xs font-medium bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-md transition-colors flex items-center gap-1.5"
          >
            <Sparkles className="w-3.5 h-3.5" />
            {isLoggingIn ? "Loading Demo..." : "Explore Demo Mode"}
          </button>
        )}

        {isAuthenticated && user && (
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2 bg-slate-900 border border-slate-800 px-3 py-1 rounded-full text-xs">
              {user.avatar_url ? (
                <img src={user.avatar_url} alt={user.name || "User"} className="w-5 h-5 rounded-full" />
              ) : (
                <User className="w-4 h-4 text-slate-400" />
              )}
              <span className="text-slate-300 font-medium">{user.login || user.name || "Developer"}</span>
              {isDemo && (
                <span className="text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.2 rounded font-mono">
                  Demo
                </span>
              )}
            </div>

            <button
              onClick={() => logout()}
              title="Sign Out"
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-900 rounded-md transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        )}

        <a
          href="https://github.com"
          target="_blank"
          rel="noreferrer"
          className="text-slate-400 hover:text-slate-200 p-1.5 rounded-md hover:bg-slate-900 transition-colors"
        >
          <Github className="w-4 h-4" />
        </a>
      </div>
    </header>
  );
}
