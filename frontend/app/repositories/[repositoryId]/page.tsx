"use client";

import { use } from "react";
import Link from "next/link";
import { FolderGit2, GitPullRequest, Settings, ArrowRight } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useRepository } from "@/hooks/useRepositories";
import { usePullRequests } from "@/hooks/usePullRequests";
import { RequireAuth } from "@/components/auth/RequireAuth";

function RepositoryDetailPage({ params }: { params: Promise<{ repositoryId: string }> }) {
  const resolvedParams = use(params);
  const repoId = resolvedParams.repositoryId;
  const { data: repo } = useRepository(repoId);
  const { data: pullRequests } = usePullRequests(repoId);

  const prList = pullRequests?.length
    ? pullRequests
    : [
        {
          id: "demo-pr-id",
          repository_id: repoId,
          github_pr_number: 42,
          title: "Add discount and checkout endpoints",
          body: "Implements coupon validation and payment processing routes.",
          author: "ritesh-kumar",
          head_ref: "feature/checkout",
          base_ref: "main",
          status: "open",
          additions: 145,
          deletions: 12,
          changed_files: 3,
          created_at: new Date().toISOString(),
          latest_analysis: {
            id: "demo-analysis-id",
            status: "completed",
            summary: "1 Critical SQL injection, 1 High Authorization Bypass found",
          },
        },
      ];

  return (
    <div className="min-h-screen bg-canvas flex text-ink">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <div className="flex items-center space-x-2">
                <FolderGit2 className="w-5 h-5 text-accent" />
                <h1 className="text-xl font-semibold text-ink">{repo?.full_name || "ecommerce-api-demo"}</h1>
                <Badge variant="outline" className="font-mono">
                  {repo?.primary_language || "Python"}
                </Badge>
              </div>
              <p className="text-xs text-ink-muted">
                {repo?.description || "E-Commerce REST API with payment, discount, and checkout routes"}
              </p>
            </div>

            <Link href="/settings">
              <Button size="sm" variant="outline" className="gap-1.5">
                <Settings className="w-3.5 h-3.5" /> Repository Settings
              </Button>
            </Link>
          </div>

          {/* Pull Requests Table */}
          <Card>
            <CardHeader>
              <CardTitle>Pull Requests ({prList.length})</CardTitle>
              <CardDescription>Select a pull request to run AI code analysis or review past reports</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {prList.map((pr) => (
                <div
                  key={pr.id}
                  className="p-4 rounded-lg border border-line bg-canvas hover:border-line transition-colors flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4"
                >
                  <div className="space-y-1">
                    <div className="flex items-center space-x-2">
                      <GitPullRequest className="w-4 h-4 text-success" />
                      <span className="font-mono text-xs text-ink-muted">#{pr.github_pr_number}</span>
                      <h3 className="font-semibold text-sm text-ink">{pr.title}</h3>
                    </div>
                    <div className="flex items-center space-x-3 text-xs text-ink-muted font-mono">
                      <span>by @{pr.author}</span>
                      <span>•</span>
                      <span className="text-success">+{pr.additions}</span>
                      <span className="text-critical">-{pr.deletions}</span>
                      <span>•</span>
                      <span>{pr.changed_files} files changed</span>
                    </div>
                  </div>

                  <div className="flex items-center space-x-3">
                    <Link href={`/pull-requests/${pr.id}`}>
                      <Button size="sm" className="gap-1.5">
                        Open Analysis Workspace <ArrowRight className="w-3.5 h-3.5" />
                      </Button>
                    </Link>
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

export default function RepositoryDetailPageRoute(props: Parameters<typeof RepositoryDetailPage>[0]) {
  return (
    <RequireAuth>
      <RepositoryDetailPage {...props} />
    </RequireAuth>
  );
}
