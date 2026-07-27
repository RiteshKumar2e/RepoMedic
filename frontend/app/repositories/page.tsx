"use client";

import Link from "next/link";
import { FolderGit2, GitPullRequest, Star, Clock, ArrowRight } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useRepositories } from "@/hooks/useRepositories";
import { formatDate } from "@/lib/utils";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { ConnectRepositories } from "@/components/repositories/ConnectRepositories";

function RepositoriesPage() {
  const { data: repositories, isLoading } = useRepositories();

  // Show what is actually connected. A placeholder repository used to render
  // here while loading, which read as real data.
  const repoList = repositories ?? [];

  return (
    <div className="min-h-screen bg-canvas flex text-ink">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-ink">Connected Repositories</h1>
              <p className="text-xs text-ink-muted mt-1">Manage scanned repositories and review configurations</p>
            </div>
            <ConnectRepositories size="sm" />
          </div>

          {isLoading && (
            <p className="text-xs text-ink-subtle">Loading repositories…</p>
          )}

          {!isLoading && repoList.length === 0 && (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
                <FolderGit2 className="h-8 w-8 text-ink-subtle" />
                <div>
                  <p className="text-sm font-medium text-ink">No repositories connected yet</p>
                  <p className="mt-1 text-xs text-ink-muted">
                    Import the repositories your GitHub account can access to start reviewing them.
                  </p>
                </div>
                <ConnectRepositories />
              </CardContent>
            </Card>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {repoList.map((repo) => (
              <Card key={repo.id} className="hover:border-line transition-colors">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <FolderGit2 className="w-5 h-5 text-accent" />
                      <CardTitle>{repo.full_name}</CardTitle>
                    </div>
                    {repo.primary_language && (
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {repo.primary_language}
                      </Badge>
                    )}
                  </div>
                  <CardDescription>{repo.description || "No description provided"}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-center justify-between text-xs text-ink-muted font-mono">
                    <span className="flex items-center gap-1">
                      <GitPullRequest className="w-3.5 h-3.5 text-medium" />
                      {repo.open_pr_count} Open PRs
                    </span>
                    <span className="flex items-center gap-1">
                      <Star className="w-3.5 h-3.5 text-medium" />
                      {repo.stars} Stars
                    </span>
                    <span className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5 text-ink-muted" />
                      {formatDate(repo.last_analyzed_at)}
                    </span>
                  </div>

                  <div className="flex items-center justify-end space-x-2 pt-2 border-t border-line">
                    <Link href={`/repositories/${repo.id}`}>
                      <Button size="sm" className="gap-1.5">
                        View Repository <ArrowRight className="w-3.5 h-3.5" />
                      </Button>
                    </Link>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </main>
      </div>
    </div>
  );
}

export default function RepositoriesPageRoute() {
  return (
    <RequireAuth>
      <RepositoriesPage />
    </RequireAuth>
  );
}
