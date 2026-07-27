"use client";

import { use, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { GitPullRequest, Play, ArrowRight } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  usePullRequest,
  usePullRequestAnalyses,
  useTriggerAnalysis,
} from "@/hooks/usePullRequests";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { APIError } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/utils";
import type { AnalysisStatus } from "@/types/api";

const ANALYSIS_BADGE: Record<AnalysisStatus, "success" | "critical" | "medium" | "neutral"> = {
  completed: "success",
  failed: "critical",
  running: "medium",
  queued: "neutral",
  cancelled: "neutral",
};

function PullRequestDetailPage({ params }: { params: Promise<{ pullRequestId: string }> }) {
  const resolvedParams = use(params);
  const prId = resolvedParams.pullRequestId;
  const { data: pr, isLoading: prLoading } = usePullRequest(prId);
  const { data: analyses, isLoading: analysesLoading } = usePullRequestAnalyses(prId);
  const triggerAnalysis = useTriggerAnalysis(prId);
  const router = useRouter();

  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleStartAnalysis = async () => {
    setIsStarting(true);
    setError(null);
    try {
      // Navigate to whatever the API actually created. This used to fall back
      // to a hardcoded "demo-analysis-id", which 404'd on every request.
      const result = await triggerAnalysis.mutateAsync({ force: true });
      router.push(`/analysis/${result.id}`);
    } catch (err) {
      setError(
        err instanceof APIError ? err.message : "Could not start the analysis. Please try again.",
      );
      setIsStarting(false);
    }
  };

  return (
    <div className="min-h-screen bg-canvas flex text-ink">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          {/* PR Header */}
          <div className="p-6 rounded-md border border-line bg-surface space-y-4">
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center space-x-3">
                  <GitPullRequest className="w-6 h-6 text-success" />
                  <span className="font-mono text-ink-muted text-sm">
                    #{pr?.github_pr_number ?? "—"}
                  </span>
                  <h1 className="text-xl font-semibold text-ink">
                    {pr?.title ?? (prLoading ? "Loading…" : "Pull request")}
                  </h1>
                </div>
                <div className="flex items-center space-x-3 text-xs text-ink-muted font-mono">
                  <span>Author: @{pr?.author ?? "unknown"}</span>
                  {pr && (
                    <>
                      <span>•</span>
                      <span>
                        Branch: {pr.head_ref} → {pr.base_ref}
                      </span>
                      <span>•</span>
                      <span className="text-success">+{pr.additions}</span>
                      <span className="text-critical">-{pr.deletions}</span>
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-center space-x-3">
                <Button
                  onClick={handleStartAnalysis}
                  disabled={isStarting || !pr}
                  className="gap-2"
                >
                  <Play className="w-4 h-4 fill-current" />
                  {isStarting ? "Initializing Pipeline..." : "Run AI Analysis"}
                </Button>
              </div>
            </div>

            {error && (
              <p role="alert" className="text-xs text-critical">
                {error}
              </p>
            )}
          </div>

          {/* Analysis History */}
          <Card>
            <CardHeader>
              <CardTitle>Analysis History</CardTitle>
              <CardDescription>Previous repository-aware reviews run on this pull request</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {analysesLoading && <p className="text-xs text-ink-subtle">Loading analyses…</p>}

              {!analysesLoading && (analyses?.length ?? 0) === 0 && (
                <p className="py-4 text-center text-xs text-ink-subtle">
                  No analysis has been run on this pull request yet. Use “Run AI Analysis” above.
                </p>
              )}

              {analyses?.map((analysis) => (
                <div
                  key={analysis.id}
                  className="p-4 rounded-lg border border-line bg-canvas flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                >
                  <div className="space-y-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={ANALYSIS_BADGE[analysis.status] ?? "neutral"}>
                        {analysis.status}
                      </Badge>
                      <span className="font-mono text-xs text-ink-muted">
                        {formatDate(analysis.created_at)}
                      </span>
                      {analysis.duration_seconds != null && (
                        <span className="font-mono text-xs text-ink-subtle">
                          {formatDuration(analysis.duration_seconds)}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-ink-muted">
                      {analysis.summary ??
                        `${analysis.files_analyzed} files analysed • stage: ${analysis.stage}`}
                    </p>
                  </div>

                  <Link href={`/analysis/${analysis.id}`} className="shrink-0">
                    <Button size="sm" variant="secondary" className="gap-1.5">
                      Open Review Workspace <ArrowRight className="w-3.5 h-3.5" />
                    </Button>
                  </Link>
                </div>
              ))}
            </CardContent>
          </Card>
        </main>
      </div>
    </div>
  );
}

export default function PullRequestDetailPageRoute(props: Parameters<typeof PullRequestDetailPage>[0]) {
  return (
    <RequireAuth>
      <PullRequestDetailPage {...props} />
    </RequireAuth>
  );
}
