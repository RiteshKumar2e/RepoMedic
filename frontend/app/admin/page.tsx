"use client";

import { ShieldCheck, Users, FolderGit2, Activity, ScrollText, AlertCircle } from "lucide-react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { useAuth } from "@/hooks/useAuth";
import { useAdminOverview } from "@/hooks/useAdmin";
import { formatDate, formatDuration } from "@/lib/utils";
import { cn } from "@/lib/utils";
import type { AnalysisStatus, Severity } from "@/types/api";

const SEVERITY_BAR: Record<Severity, string> = {
  critical: "bg-critical",
  high: "bg-high",
  medium: "bg-medium",
  low: "bg-low",
  informational: "bg-info",
};

const STATUS_BADGE: Record<AnalysisStatus, "success" | "critical" | "medium" | "neutral"> = {
  completed: "success",
  failed: "critical",
  running: "medium",
  queued: "neutral",
  cancelled: "neutral",
};

const AUTH_LABEL: Record<string, string> = {
  github: "GitHub",
  password: "Password",
  none: "—",
  unknown: "—",
};

/** Wide tables must scroll inside their own container, never the page. */
function TableShell({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto">{children}</div>;
}

function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return (
    <th
      className={cn(
        "whitespace-nowrap px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-ink-subtle",
        className,
      )}
    >
      {children}
    </th>
  );
}

function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={cn("whitespace-nowrap px-3 py-2 text-[13px]", className)}>{children}</td>;
}

function AdminPage() {
  const { isAdmin, isLoading: authLoading } = useAuth();
  const { data, isLoading, error } = useAdminOverview();

  if (!authLoading && !isAdmin) {
    return (
      <div className="min-h-screen bg-canvas flex text-ink">
        <Sidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <Header />
          <main className="flex-1 p-6">
            <Card>
              <CardContent className="flex flex-col items-center gap-3 p-10 text-center">
                <AlertCircle className="h-8 w-8 text-medium" />
                <div>
                  <p className="text-sm font-medium text-ink">Administrator access required</p>
                  <p className="mt-1 max-w-md text-xs text-ink-muted">
                    This page shows data across every account. Access is granted by the
                    <code className="mx-1 font-mono">ADMIN_EMAILS</code> allowlist on the server —
                    add your account email there and sign in again.
                  </p>
                </div>
              </CardContent>
            </Card>
          </main>
        </div>
      </div>
    );
  }

  const totals = data?.totals;
  const findings = data?.findings;
  const totalFindings = findings?.total ?? 0;

  const tiles = [
    { label: "Users", value: totals?.users, icon: Users },
    { label: "Repositories", value: totals?.repositories, icon: FolderGit2 },
    { label: "Analyses", value: totals?.analyses, icon: Activity },
    { label: "Findings", value: totals?.findings, icon: ShieldCheck },
  ];

  return (
    <div className="min-h-screen bg-canvas flex text-ink">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className="flex-1 space-y-6 overflow-y-auto p-6">
          <div>
            <h1 className="flex items-center gap-2 text-xl font-semibold text-ink">
              <ShieldCheck className="h-5 w-5 text-accent" /> Admin
            </h1>
            <p className="mt-1 text-xs text-ink-muted">
              Every account, repository, analysis and audit entry in this deployment.
            </p>
          </div>

          {isLoading && <p className="text-xs text-ink-subtle">Loading system data…</p>}

          {error && (
            <Card>
              <CardContent className="p-4">
                <p className="text-xs text-critical">
                  Could not load admin data: {(error as Error).message}
                </p>
              </CardContent>
            </Card>
          )}

          {data && (
            <>
              {/* Totals */}
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
                {tiles.map(({ label, value, icon: Icon }) => (
                  <Card key={label}>
                    <CardContent className="flex items-center justify-between p-4">
                      <div>
                        <p className="text-xs font-medium text-ink-muted">{label}</p>
                        <h3 className="mt-1 text-2xl font-semibold text-ink">{value ?? 0}</h3>
                      </div>
                      <span className="flex h-10 w-10 items-center justify-center rounded-lg border border-accent-line bg-accent-soft text-accent">
                        <Icon className="h-5 w-5" />
                      </span>
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Findings & patches */}
              <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle>Findings by severity</CardTitle>
                    <CardDescription>Across every repository in the system</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {totalFindings === 0 ? (
                      <p className="text-xs text-ink-subtle">No findings recorded yet.</p>
                    ) : (
                      findings?.by_severity.map((entry) => {
                        const percent = Math.round((entry.count / totalFindings) * 100);
                        return (
                          <div key={entry.severity} className="space-y-1">
                            <div className="flex items-center justify-between text-xs">
                              <span className="font-medium capitalize text-ink">
                                {entry.severity}
                              </span>
                              <span className="font-mono text-ink-muted">
                                {entry.count} ({percent}%)
                              </span>
                            </div>
                            <div className="h-2 w-full overflow-hidden rounded-full bg-inset">
                              <div
                                className={`h-full ${SEVERITY_BAR[entry.severity] ?? "bg-info"}`}
                                style={{ width: `${percent}%` }}
                              />
                            </div>
                          </div>
                        );
                      })
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Patches</CardTitle>
                    <CardDescription>Proposed fixes and how they were decided</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="grid grid-cols-3 gap-3 text-center">
                      <div>
                        <p className="text-2xl font-semibold text-ink">
                          {findings?.patches_proposed ?? 0}
                        </p>
                        <p className="text-[11px] text-ink-muted">Proposed</p>
                      </div>
                      <div>
                        <p className="text-2xl font-semibold text-success">
                          {findings?.patches_approved ?? 0}
                        </p>
                        <p className="text-[11px] text-ink-muted">Approved</p>
                      </div>
                      <div>
                        <p className="text-2xl font-semibold text-critical">
                          {findings?.patches_rejected ?? 0}
                        </p>
                        <p className="text-[11px] text-ink-muted">Rejected</p>
                      </div>
                    </div>
                    <p className="text-xs text-ink-muted">
                      Fix acceptance rate{" "}
                      <span className="font-semibold text-ink">
                        {findings?.fix_acceptance_rate ?? 0}%
                      </span>{" "}
                      — of the patches a human actually decided on.
                    </p>

                    {(findings?.by_category.length ?? 0) > 0 && (
                      <div className="flex flex-wrap gap-1.5 border-t border-line pt-3">
                        {findings?.by_category.map((entry) => (
                          <Badge key={entry.category} variant="neutral">
                            {entry.category} · {entry.count}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>

              {/* Users */}
              <Card>
                <CardHeader>
                  <CardTitle>Users ({data.users.length})</CardTitle>
                  <CardDescription>Every account in this deployment</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  <TableShell>
                    <table className="w-full">
                      <thead className="border-b border-line bg-surface">
                        <tr>
                          <Th>User</Th>
                          <Th>Email</Th>
                          <Th>Sign-in</Th>
                          <Th>GitHub</Th>
                          <Th className="text-right">Repos</Th>
                          <Th className="text-right">Analyses</Th>
                          <Th>Joined</Th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line-muted">
                        {data.users.map((user) => (
                          <tr key={user.id} className="row-hover">
                            <Td>
                              <span className="flex items-center gap-2">
                                <span className="font-medium text-ink">
                                  {user.name || user.login || "—"}
                                </span>
                                {user.is_admin && <Badge variant="default">admin</Badge>}
                              </span>
                            </Td>
                            <Td className="font-mono text-ink-muted">{user.email || "—"}</Td>
                            <Td className="text-ink-muted">
                              {AUTH_LABEL[user.auth_method] ?? user.auth_method}
                            </Td>
                            <Td>
                              {user.github_connected ? (
                                <Badge variant="success">connected</Badge>
                              ) : (
                                <span className="text-ink-subtle">—</span>
                              )}
                            </Td>
                            <Td className="text-right font-mono text-ink">
                              {user.repository_count}
                            </Td>
                            <Td className="text-right font-mono text-ink">{user.analysis_count}</Td>
                            <Td className="text-ink-muted">{formatDate(user.created_at)}</Td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </TableShell>
                </CardContent>
              </Card>

              {/* Repositories */}
              <Card>
                <CardHeader>
                  <CardTitle>Repositories ({data.repositories.length})</CardTitle>
                  <CardDescription>Connected across every account</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  {data.repositories.length === 0 ? (
                    <p className="p-4 text-xs text-ink-subtle">No repositories connected yet.</p>
                  ) : (
                    <TableShell>
                      <table className="w-full">
                        <thead className="border-b border-line bg-surface">
                          <tr>
                            <Th>Repository</Th>
                            <Th>Owner</Th>
                            <Th>Language</Th>
                            <Th className="text-right">Analyses</Th>
                            <Th className="text-right">Findings</Th>
                            <Th>Last analysed</Th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line-muted">
                          {data.repositories.map((repo) => (
                            <tr key={repo.id} className="row-hover">
                              <Td>
                                <span className="flex items-center gap-2">
                                  <span className="font-medium text-ink">{repo.full_name}</span>
                                  {repo.is_private && <Badge variant="neutral">private</Badge>}
                                </span>
                              </Td>
                              <Td className="text-ink-muted">{repo.owner_login || "—"}</Td>
                              <Td className="text-ink-muted">{repo.primary_language || "—"}</Td>
                              <Td className="text-right font-mono text-ink">
                                {repo.analysis_count}
                              </Td>
                              <Td className="text-right font-mono text-ink">
                                {repo.finding_count}
                              </Td>
                              <Td className="text-ink-muted">
                                {repo.last_analyzed_at ? formatDate(repo.last_analyzed_at) : "never"}
                              </Td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </TableShell>
                  )}
                </CardContent>
              </Card>

              {/* Analyses */}
              <Card>
                <CardHeader>
                  <CardTitle>Recent analyses ({data.analyses.length})</CardTitle>
                  <CardDescription>Newest first, across all repositories</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  {data.analyses.length === 0 ? (
                    <p className="p-4 text-xs text-ink-subtle">No analyses have run yet.</p>
                  ) : (
                    <TableShell>
                      <table className="w-full">
                        <thead className="border-b border-line bg-surface">
                          <tr>
                            <Th>Repository</Th>
                            <Th>Target</Th>
                            <Th>Status</Th>
                            <Th>Trigger</Th>
                            <Th className="text-right">Findings</Th>
                            <Th className="text-right">Duration</Th>
                            <Th>Started</Th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line-muted">
                          {data.analyses.map((analysis) => (
                            <tr key={analysis.id} className="row-hover">
                              <Td className="text-ink">{analysis.repository_full_name || "—"}</Td>
                              <Td className="font-mono text-ink-muted">
                                {analysis.pull_request_number
                                  ? `#${analysis.pull_request_number}`
                                  : "full scan"}
                              </Td>
                              <Td>
                                <Badge variant={STATUS_BADGE[analysis.status] ?? "neutral"}>
                                  {analysis.status}
                                </Badge>
                              </Td>
                              <Td className="text-ink-muted">{analysis.triggered_by}</Td>
                              <Td className="text-right font-mono text-ink">
                                {analysis.finding_count}
                              </Td>
                              <Td className="text-right font-mono text-ink-muted">
                                {analysis.duration_seconds != null
                                  ? formatDuration(analysis.duration_seconds)
                                  : "—"}
                              </Td>
                              <Td className="text-ink-muted">{formatDate(analysis.created_at)}</Td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </TableShell>
                  )}
                </CardContent>
              </Card>

              {/* Audit log */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <ScrollText className="h-4 w-4 text-accent" /> Audit log ({data.audit.length})
                  </CardTitle>
                  <CardDescription>Who did what, and when</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  {data.audit.length === 0 ? (
                    <p className="p-4 text-xs text-ink-subtle">Nothing recorded yet.</p>
                  ) : (
                    <TableShell>
                      <table className="w-full">
                        <thead className="border-b border-line bg-surface">
                          <tr>
                            <Th>Action</Th>
                            <Th>Entity</Th>
                            <Th>Actor</Th>
                            <Th>IP</Th>
                            <Th>When</Th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-line-muted">
                          {data.audit.map((entry) => (
                            <tr key={entry.id} className="row-hover">
                              <Td className="font-mono text-ink">{entry.action}</Td>
                              <Td className="text-ink-muted">{entry.entity_type}</Td>
                              <Td className="text-ink-muted">
                                {entry.actor_login || entry.actor_email || "—"}
                              </Td>
                              <Td className="font-mono text-ink-subtle">
                                {entry.ip_address || "—"}
                              </Td>
                              <Td className="text-ink-muted">{formatDate(entry.created_at)}</Td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </TableShell>
                  )}
                </CardContent>
              </Card>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

export default function AdminPageRoute() {
  return (
    <RequireAuth>
      <AdminPage />
    </RequireAuth>
  );
}
