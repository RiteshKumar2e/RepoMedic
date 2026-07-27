"use client";

import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";

import { BarChart3 } from "lucide-react";
import { useAnalytics } from "@/hooks/useAnalytics";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { formatDuration } from "@/lib/utils";
import type { Severity } from "@/types/api";

const SEVERITY_BAR: Record<Severity, string> = {
  critical: "bg-critical",
  high: "bg-high",
  medium: "bg-medium",
  low: "bg-low",
  informational: "bg-info",
};

function AnalyticsPage() {
  const { data: analytics, isLoading } = useAnalytics();

  const totalFindings = analytics?.total_findings ?? 0;
  const severities = analytics?.findings_by_severity ?? [];
  // Percentages are of the total, so an empty workspace renders empty bars
  // rather than dividing by zero.
  const breakdown = severities.map((entry) => ({
    ...entry,
    percent: totalFindings ? Math.round((entry.count / totalFindings) * 100) : 0,
  }));
  const severityCaption =
    breakdown
      .filter((entry) => entry.count > 0)
      .map((entry) => `${entry.count} ${entry.severity}`)
      .join(", ") || "No findings recorded yet";

  return (
    <div className="min-h-screen bg-canvas flex text-ink">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          {/* Header */}
          <div>
            <h1 className="text-xl font-semibold text-ink flex items-center gap-2">
              <BarChart3 className="w-5 h-5 text-accent" /> Platform Analytics & Posture
            </h1>
            <p className="text-xs text-ink-muted mt-1">
              Code quality trends, fix acceptance rates, defect categories, and high-risk modules
            </p>
          </div>

          {/* Metrics Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Fix Acceptance Rate</CardTitle>
                <CardDescription>Percentage of AI proposals approved</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="text-3xl font-extrabold text-success">
                  {Math.round(analytics?.fix_acceptance_rate ?? 0)}%
                </div>
                <p className="text-xs text-ink-muted">
                  {analytics?.patches_pending_review ?? 0} patches still awaiting review
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Average Review Duration</CardTitle>
                <CardDescription>Full pipeline execution time</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="text-3xl font-extrabold text-accent">
                  {formatDuration(analytics?.average_review_seconds ?? 0)}
                </div>
                <p className="text-xs text-ink-muted">Deterministic scans + AST + Parallel AI agents</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Total Findings Analyzed</CardTitle>
                <CardDescription>Across all open pull requests</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="text-3xl font-extrabold text-ink">{totalFindings}</div>
                <p className="text-xs text-ink-muted">{severityCaption}</p>
              </CardContent>
            </Card>
          </div>

          {/* Severity Distribution */}
          <Card>
            <CardHeader>
              <CardTitle>Findings by Severity</CardTitle>
              <CardDescription>Breakdown across every analysed pull request</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {isLoading && (
                <p className="text-xs text-ink-subtle">Loading analytics…</p>
              )}

              {!isLoading && totalFindings === 0 && (
                <p className="text-xs text-ink-subtle">
                  No findings yet. Run an analysis on a pull request to populate this report.
                </p>
              )}

              {!isLoading &&
                totalFindings > 0 &&
                breakdown.map((entry) => (
                  <div key={entry.severity} className="space-y-1">
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium capitalize text-ink">{entry.severity}</span>
                      <span className="font-mono text-ink-muted">
                        {entry.count} ({entry.percent}%)
                      </span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-inset">
                      <div
                        className={`h-full ${SEVERITY_BAR[entry.severity]}`}
                        style={{ width: `${entry.percent}%` }}
                      />
                    </div>
                  </div>
                ))}
            </CardContent>
          </Card>
        </main>
      </div>
    </div>
  );
}

export default function AnalyticsPageRoute() {
  return (
    <RequireAuth>
      <AnalyticsPage />
    </RequireAuth>
  );
}
