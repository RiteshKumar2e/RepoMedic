"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

import { GitFork, FileCode2, ShieldCheck } from "lucide-react";
import { useRepositoryGraph } from "@/hooks/useGraph";
import { useRepositories } from "@/hooks/useRepositories";
import { RequireAuth } from "@/components/auth/RequireAuth";
import { RepositorySelect } from "@/components/repositories/RepositorySelect";
import { ConnectRepositories } from "@/components/repositories/ConnectRepositories";

function ArchitectureGraphPage() {
  const { data: repositories, isLoading: reposLoading } = useRepositories();
  const [pickedRepository, setPickedRepository] = useState<string | null>(null);
  const [pickedNode, setPickedNode] = useState<string | null>(null);

  // Both selections are derived rather than synced through an effect: fall back
  // to the first available item until the user picks one. The page used to
  // request a hardcoded "demo-repo-id", which always 404'd.
  const repositoryId = pickedRepository ?? repositories?.[0]?.id ?? null;

  const { data: graph, isLoading: graphLoading } = useRepositoryGraph(repositoryId ?? "");

  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  // Guards against a stale selection after switching repository.
  const selectedNode =
    pickedNode && nodes.some((node) => node.id === pickedNode)
      ? pickedNode
      : (nodes[0]?.id ?? null);

  const labelFor = (id: string) => nodes.find((node) => node.id === id)?.label ?? id;

  const outbound = edges.filter((edge) => edge.source === selectedNode);
  const inbound = edges.filter((edge) => edge.target === selectedNode);
  const coveringTests = inbound.filter((edge) => edge.type === "tests");
  const dependents = inbound.filter((edge) => edge.type !== "tests");

  const hasRepositories = Boolean(repositories?.length);

  return (
    <div className="h-screen bg-canvas flex text-ink overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-full">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          {/* Header */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-xl font-semibold text-ink flex items-center gap-2">
                <GitFork className="w-5 h-5 text-accent" /> Repository Knowledge Graph
              </h1>
              <p className="text-xs text-ink-muted mt-1">
                Visualizing modules, symbol calls, database model dependencies, and test coverage blast radius
              </p>
            </div>

            <RepositorySelect
              repositories={repositories ?? []}
              value={repositoryId}
              onChange={(id) => {
                setPickedRepository(id);
                setPickedNode(null);
              }}
              isLoading={reposLoading}
            />
          </div>

          {!reposLoading && !hasRepositories && (
            <Card>
              <CardContent className="space-y-3 p-6">
                <p className="text-sm font-medium text-ink">No repositories connected yet</p>
                <p className="text-xs text-ink-muted">
                  Connect a repository to build its knowledge graph.
                </p>
                <ConnectRepositories size="sm" />
              </CardContent>
            </Card>
          )}

          {hasRepositories && (
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Interactive Graph Display */}
              <Card className="lg:col-span-2 min-h-[500px] flex flex-col">
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle>Module Dependency Canvas</CardTitle>
                  <Badge variant="outline" className="font-mono text-[10px]">
                    {nodes.length} Nodes • {edges.length} Edges
                  </Badge>
                </CardHeader>
                <CardContent className="flex-1 relative bg-canvas rounded-b-lg border-t border-line p-6 flex items-center justify-center">
                  {graphLoading && (
                    <p className="text-xs text-ink-subtle">Loading knowledge graph…</p>
                  )}

                  {!graphLoading && nodes.length === 0 && (
                    <p className="max-w-sm text-center text-xs text-ink-subtle">
                      No graph yet for this repository. The graph is built during analysis — run one
                      on a pull request to populate it.
                    </p>
                  )}

                  {!graphLoading && nodes.length > 0 && (
                    <div className="w-full max-w-lg space-y-6">
                      {nodes.map((node) => {
                        const isSelected = selectedNode === node.id;
                        return (
                          <div
                            key={node.id}
                            onClick={() => setPickedNode(node.id)}
                            className={`p-4 rounded-lg border cursor-pointer transition-all flex items-center justify-between ${
                              isSelected
                                ? "bg-accent-soft border-accent-line text-accent shadow-sm shadow-sky-500/10"
                                : node.changed
                                ? "bg-medium-soft border-medium-line text-medium"
                                : "bg-surface border-line text-ink hover:border-line"
                            }`}
                          >
                            <div className="flex items-center space-x-3">
                              <FileCode2 className="w-5 h-5 text-accent" />
                              <div>
                                <span className="font-mono text-xs font-semibold">{node.label}</span>
                                <span className="text-[10px] block text-ink-muted capitalize">
                                  Type: {node.type}
                                  {node.finding_count > 0 && ` • ${node.finding_count} findings`}
                                </span>
                              </div>
                            </div>

                            {node.changed && <Badge variant="high">Modified in PR</Badge>}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* Selected Node Blast Radius Detail */}
              <Card>
                <CardHeader>
                  <CardTitle>Blast Radius & Impact Analysis</CardTitle>
                  <CardDescription>Dependent modules affected by changes</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {selectedNode ? (
                    <div className="space-y-3">
                      <div className="p-3 rounded bg-canvas border border-line">
                        <span className="text-[11px] font-mono text-ink-muted block mb-1">
                          Selected Target
                        </span>
                        <span className="font-mono text-xs text-accent font-semibold break-all">
                          {labelFor(selectedNode)}
                        </span>
                      </div>

                      <div className="space-y-2">
                        <span className="text-xs font-semibold text-ink">
                          Outbound Imports / Reads:
                        </span>
                        {outbound.length === 0 ? (
                          <p className="text-xs text-ink-subtle">No outbound dependencies.</p>
                        ) : (
                          outbound.map((edge) => (
                            <div
                              key={edge.id}
                              className="p-2.5 rounded bg-canvas border border-line text-xs font-mono text-ink"
                            >
                              → {labelFor(edge.target)}{" "}
                              <span className="text-ink-subtle">({edge.type})</span>
                            </div>
                          ))
                        )}
                      </div>

                      <div className="space-y-2">
                        <span className="text-xs font-semibold text-ink">Impacted by a change:</span>
                        {dependents.length === 0 ? (
                          <p className="text-xs text-ink-subtle">Nothing depends on this node.</p>
                        ) : (
                          dependents.map((edge) => (
                            <div
                              key={edge.id}
                              className="p-2.5 rounded bg-canvas border border-line text-xs font-mono text-ink"
                            >
                              ← {labelFor(edge.source)}{" "}
                              <span className="text-ink-subtle">({edge.type})</span>
                            </div>
                          ))
                        )}
                      </div>

                      <div className="space-y-2">
                        <span className="text-xs font-semibold text-ink">Covering Test Suites:</span>
                        {coveringTests.length === 0 ? (
                          <p className="text-xs text-ink-subtle">
                            No test file references this node — changes here are uncovered.
                          </p>
                        ) : (
                          coveringTests.map((edge) => (
                            <div
                              key={edge.id}
                              className="p-2.5 rounded bg-success-soft border border-success-line text-xs font-mono text-success flex items-center gap-2"
                            >
                              <ShieldCheck className="w-4 h-4 shrink-0" /> {labelFor(edge.source)}
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-ink-subtle">Click a node on the canvas to inspect blast radius.</p>
                  )}
                </CardContent>
              </Card>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

export default function ArchitectureGraphPageRoute() {
  return (
    <RequireAuth>
      <ArchitectureGraphPage />
    </RequireAuth>
  );
}
