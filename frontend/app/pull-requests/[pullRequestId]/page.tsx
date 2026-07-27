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
import { usePullRequest, useTriggerAnalysis } from "@/hooks/usePullRequests";
import { RequireAuth } from "@/components/auth/RequireAuth";

function PullRequestDetailPage({ params }: { params: Promise<{ pullRequestId: string }> }) {
  const resolvedParams = use(params);
  const prId = resolvedParams.pullRequestId;
  const { data: pr } = usePullRequest(prId);
  const triggerAnalysis = useTriggerAnalysis(prId);
  const router = useRouter();

  const [isStarting, setIsStarting] = useState(false);

  const handleStartAnalysis = async () => {
    setIsStarting(true);
    try {
      const result = await triggerAnalysis.mutateAsync({ force: true });
      if (result.id) {
        router.push(`/analysis/${result.id}`);
      } else {
        router.push(`/analysis/demo-analysis-id`);
      }
    } catch {
      // Demo fallback
      router.push(`/analysis/demo-analysis-id`);
    } finally {
      setIsStarting(false);
    }
  };

  const title = pr?.title || "Add discount and checkout endpoints";
  const prNumber = pr?.github_pr_number || 42;
  const author = pr?.author || "ritesh-kumar";

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
                  <span className="font-mono text-ink-muted text-sm">#{prNumber}</span>
                  <h1 className="text-xl font-semibold text-ink">{title}</h1>
                </div>
                <div className="flex items-center space-x-3 text-xs text-ink-muted font-mono">
                  <span>Author: @{author}</span>
                  <span>•</span>
                  <span>Branch: feature/checkout → main</span>
                </div>
              </div>

              <div className="flex items-center space-x-3">
                <Button onClick={handleStartAnalysis} disabled={isStarting} className="gap-2">
                  <Play className="w-4 h-4 fill-current" />
                  {isStarting ? "Initializing Pipeline..." : "Run AI Analysis"}
                </Button>
              </div>
            </div>
          </div>

          {/* Analysis History */}
          <Card>
            <CardHeader>
              <CardTitle>Analysis History</CardTitle>
              <CardDescription>Previous repository-aware reviews run on this pull request</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="p-4 rounded-lg border border-line bg-canvas flex items-center justify-between">
                <div className="space-y-1">
                  <div className="flex items-center space-x-2">
                    <Badge variant="critical">Do Not Merge</Badge>
                    <span className="text-xs font-semibold text-ink">Analysis #demo-analysis-id</span>
                  </div>
                  <p className="text-xs text-ink-muted">
                    7 issues detected (1 Critical SQL Injection, 1 High Auth Bypass, 1 High Secret). 3 patches validated.
                  </p>
                </div>

                <Link href="/analysis/demo-analysis-id">
                  <Button size="sm" variant="secondary" className="gap-1.5">
                    Open Review Workspace <ArrowRight className="w-3.5 h-3.5" />
                  </Button>
                </Link>
              </div>
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
