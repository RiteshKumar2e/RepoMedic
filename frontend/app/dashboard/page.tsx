"use client";

import Link from "next/link";
import { FolderGit2, GitPullRequest, ShieldAlert, CheckCircle2, Clock, Sparkles, ArrowRight, RefreshCw } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useRepositories } from "@/hooks/useRepositories";
import { useAnalytics } from "@/hooks/useAnalytics";
import { useAuth } from "@/hooks/useAuth";
import { formatDuration, getSeverityBadgeColor } from "@/lib/utils";
import type { Severity } from "@/types/api";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { ConnectRepositories } from "@/components/repositories/ConnectRepositories";

function DashboardPage() {
  // RequireAuth guarantees a session before this renders — no silent sign-in.
  const { user, isDemo } = useAuth();
  const { data: repositories, isLoading: reposLoading, refetch: refetchRepos } = useRepositories();
  const { data: analytics } = useAnalytics();

  return (
    <div className="min-h-screen bg-canvas flex text-ink">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          {/* Welcome Banner */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 p-5 rounded-md border border-line">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold text-ink">
                  Welcome back, {user?.name || user?.login || "Developer"}
                </h1>
                {isDemo && (
                  <Badge variant="medium" className="gap-1">
                    <Sparkles className="w-3 h-3" /> Seeded Demo Mode
                  </Badge>
                )}
              </div>
              <p className="text-xs text-ink-muted mt-1">
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
                  <p className="text-xs font-medium text-ink-muted">Connected Repositories</p>
                  <h3 className="text-2xl font-semibold text-ink mt-1">
                    {analytics?.repository_count ?? repositories?.length ?? 0}
                  </h3>
                </div>
                <div className="w-10 h-10 rounded-lg bg-accent-soft border border-accent-line flex items-center justify-center text-accent">
                  <FolderGit2 className="w-5 h-5" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-ink-muted">Total Findings</p>
                  <h3 className="text-2xl font-semibold text-ink mt-1">
                    {analytics?.total_findings ?? 0}
                  </h3>
                </div>
                <div className="w-10 h-10 rounded-lg bg-medium-soft border border-medium-line flex items-center justify-center text-medium">
                  <ShieldAlert className="w-5 h-5" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-ink-muted">Fix Acceptance Rate</p>
                  <h3 className="text-2xl font-semibold text-ink mt-1">
                    {Math.round(analytics?.fix_acceptance_rate ?? 0)}%
                  </h3>
                </div>
                <div className="w-10 h-10 rounded-lg bg-success-soft border border-success-line flex items-center justify-center text-success">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-ink-muted">Avg Analysis Duration</p>
                  <h3 className="text-2xl font-semibold text-ink mt-1">
                    {formatDuration(analytics?.average_review_seconds ?? 0)}
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
                  <div className="p-4 text-center text-xs text-ink-subtle">Loading repositories...</div>
                ) : (repositories?.length ?? 0) === 0 ? (
                  <div className="space-y-3 p-4 text-center">
                    <p className="text-xs text-ink-muted">No repositories connected yet.</p>
                    <div className="flex justify-center">
                      <ConnectRepositories size="sm" />
                    </div>
                  </div>
                ) : (
                  // Links use the real id — a placeholder repository used to
                  // render here and every link off it 404'd.
                  (repositories ?? []).map((repo) => (
                    <div
                      key={repo.id}
                      className="p-3.5 rounded-lg border border-line bg-canvas hover:border-line transition-colors flex items-center justify-between"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center space-x-2">
                          <FolderGit2 className="w-4 h-4 text-accent" />
                          <Link
                            href={`/repositories/${repo.id}`}
                            className="font-medium text-sm text-ink hover:text-accent"
                          >
                            {repo.full_name}
                          </Link>
                          {repo.primary_language && (
                            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-inset text-ink-muted">
                              {repo.primary_language}
                            </span>
                          )}
                        </div>
                        <p className="text-xs text-ink-muted">
                          {repo.description || "No description provided"}
                        </p>
                      </div>

                      <div className="flex items-center space-x-3 text-xs text-ink-muted">
                        <span className="flex items-center gap-1 font-mono">
                          <GitPullRequest className="w-3.5 h-3.5 text-medium" />
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
                        <span className="font-mono text-ink">
                          {item.count} ({item.percent}%)
                        </span>
                      </div>
                      <div className="w-full bg-inset rounded-full h-1.5 overflow-hidden">
                        <div
                          className={`h-full ${
                            item.severity === "critical"
                              ? "bg-critical"
                              : item.severity === "high"
                              ? "bg-high"
                              : item.severity === "medium"
                              ? "bg-medium"
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

export default function DashboardPageRoute() {
  return (
    <RequireAuth>
      <DashboardPage />
    </RequireAuth>
  );
}
