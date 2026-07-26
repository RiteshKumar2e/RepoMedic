"use client";

import { useEffect } from "react";
import Link from "next/link";
import {
  FolderGit2,
  GitPullRequest,
  ShieldAlert,
  CheckCircle2,
  Zap,
  Clock,
  Sparkles,
  ArrowRight,
  RefreshCw,
  GitFork,
} from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useRepositories } from "@/hooks/useRepositories";
import { useAnalytics } from "@/hooks/useAnalytics";
import { useAuth } from "@/hooks/useAuth";
import { formatDate, formatDuration, getSeverityBadgeColor } from "@/lib/utils";
import type { Severity } from "@/types/api";

export default function DashboardPage() {
  const { user, isDemo, demoLogin } = useAuth();
  const { data: repositories, isLoading: reposLoading, refetch: refetchRepos } = useRepositories();
  const { data: analytics } = useAnalytics();

  // Auto-login as demo user if not logged in
  useEffect(() => {
    if (!user) {
      demoLogin();
    }
  }, [user, demoLogin]);

  return (
    <div className="min-h-screen bg-slate-950 flex text-slate-100">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          {/* Welcome Banner */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 rounded-xl border border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900 to-sky-950/30">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-bold text-slate-100">
                  Welcome back, {user?.name || user?.login || "Developer"}
                </h1>
                {isDemo && (
                  <Badge variant="medium" className="gap-1">
                    <Sparkles className="w-3 h-3" /> Seeded Demo Mode
                  </Badge>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Repository-aware AI analysis and 6-step fix validation active.
              </p>
            </div>

            <Button size="sm" variant="outline" onClick={() => refetchRepos()} className="gap-1.5">
              <RefreshCw className="w-3.5 h-3.5" /> Refresh Dashboard
            </Button>
          </div>

          {/* Metrics Overview Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-400">Connected Repositories</p>
                  <h3 className="text-2xl font-bold text-slate-100 mt-1">
                    {repositories?.length || 1}
                  </h3>
                </div>
                <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
                  <FolderGit2 className="w-5 h-5" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-400">Total Findings</p>
                  <h3 className="text-2xl font-bold text-slate-100 mt-1">
                    {analytics?.total_findings_count ?? 7}
                  </h3>
                </div>
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
                  <ShieldAlert className="w-5 h-5" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-400">Fix Acceptance Rate</p>
                  <h3 className="text-2xl font-bold text-slate-100 mt-1">
                    {analytics?.fix_acceptance_rate ?? 100}%
                  </h3>
                </div>
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-slate-400">Avg Analysis Duration</p>
                  <h3 className="text-2xl font-bold text-slate-100 mt-1">
                    {formatDuration(analytics?.average_analysis_duration ?? 4.2)}
                  </h3>
                </div>
                <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                  <Clock className="w-5 h-5" />
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Repositories & Open Pull Requests */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Repositories List */}
            <Card className="lg:col-span-2">
              <CardHeader className="flex flex-row items-center justify-between">
                <div>
                  <CardTitle>Connected Repositories</CardTitle>
                  <CardDescription>Select a repository to inspect pull requests and analyses</CardDescription>
                </div>
                <Link href="/repositories">
                  <Button size="sm" variant="ghost" className="gap-1">
                    View All <ArrowRight className="w-3.5 h-3.5" />
                  </Button>
                </Link>
              </CardHeader>
              <CardContent className="space-y-3">
                {reposLoading ? (
                  <div className="p-4 text-center text-xs text-slate-500">Loading repositories...</div>
                ) : (
                  (repositories || [
                    {
                      id: "demo-repo-id",
                      full_name: "ecommerce-api-demo",
                      owner: "repomedic-demo",
                      name: "ecommerce-api-demo",
                      description: "E-Commerce REST API with payment, discount, and checkout routes",
                      primary_language: "Python",
                      open_pr_count: 1,
                      stars: 42,
                      last_analyzed_at: new Date().toISOString(),
                    },
                  ]).map((repo) => (
                    <div
                      key={repo.id}
                      className="p-3.5 rounded-lg border border-slate-800 bg-slate-950/50 hover:border-slate-700 transition-colors flex items-center justify-between"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center space-x-2">
                          <FolderGit2 className="w-4 h-4 text-sky-400" />
                          <Link
                            href={`/repositories/${repo.id}`}
                            className="font-medium text-sm text-slate-200 hover:text-sky-400"
                          >
                            {repo.full_name}
                          </Link>
                          {repo.primary_language && (
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                              {repo.primary_language}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-slate-400">
                          {repo.description || "No description provided"}
                        </p>
                      </div>

                      <div className="flex items-center space-x-3 text-xs text-slate-400">
                        <span className="flex items-center gap-1 font-mono">
                          <GitPullRequest className="w-3.5 h-3.5 text-amber-400" />
                          {repo.open_pr_count} open PR
                        </span>
                        <Link href={`/repositories/${repo.id}`}>
                          <Button size="sm" variant="secondary">
                            Inspect
                          </Button>
                        </Link>
                      </div>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            {/* Findings by Severity Breakdown */}
            <Card>
              <CardHeader>
                <CardTitle>Findings Severity Breakdown</CardTitle>
                <CardDescription>Distribution across all active repositories</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {[
                  { severity: "critical", count: 1, percent: 14 },
                  { severity: "high", count: 2, percent: 29 },
                  { severity: "medium", count: 3, percent: 43 },
                  { severity: "low", count: 1, percent: 14 },
                ].map((item) => {
                  const style = getSeverityBadgeColor(item.severity as Severity);
                  return (
                    <div key={item.severity} className="space-y-1">
                      <div className="flex items-center justify-between text-xs font-medium">
                        <span className={`capitalize ${style.text}`}>{item.severity}</span>
                        <span className="font-mono text-slate-300">
                          {item.count} ({item.percent}%)
                        </span>
                      </div>
                      <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                        <div
                          className={`h-full ${
                            item.severity === "critical"
                              ? "bg-red-500"
                              : item.severity === "high"
                              ? "bg-orange-500"
                              : item.severity === "medium"
                              ? "bg-amber-500"
                              : "bg-blue-500"
                          }`}
                          style={{ width: `${item.percent}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    </div>
  );
}
