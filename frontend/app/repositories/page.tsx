"use client";

import Link from "next/link";
import { FolderGit2, GitPullRequest, Star, Clock, ShieldCheck, ArrowRight } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { useRepositories } from "@/hooks/useRepositories";
import { formatDate } from "@/lib/utils";
import { RequireAuth } from "@/components/auth/RequireAuth";

function RepositoriesPage() {
  const { data: repositories, isLoading } = useRepositories();

  const repoList = repositories?.length
    ? repositories
    : [
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
      ];

  return (
    <div className="min-h-screen bg-canvas flex text-ink">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-ink">Connected Repositories</h1>
              <p className="text-xs text-ink-muted mt-1">Manage scanned repositories and review configurations</p>
            </div>
          </div>

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
