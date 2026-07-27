"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";

import { GitFork, FileCode2, ShieldCheck } from "lucide-react";
import { useRepositoryGraph } from "@/hooks/useGraph";
import { RequireAuth } from "@/components/auth/RequireAuth";

const SEEDED_GRAPH_NODES = [
  { id: "file:app/api/checkout.py", label: "checkout.py", type: "module", changed: true, language: "python" },
  { id: "file:app/services/discounts.py", label: "discounts.py", type: "module", changed: true, language: "python" },
  { id: "file:app/models/discount.py", label: "discount.py (SQLModel)", type: "model", changed: false, language: "python" },
  { id: "file:tests/test_checkout.py", label: "test_checkout.py", type: "test", changed: true, language: "python" },
  { id: "file:app/core/config.py", label: "config.py", type: "module", changed: false, language: "python" },
];

const SEEDED_GRAPH_EDGES = [
  { id: "e1", source: "file:app/api/checkout.py", target: "file:app/services/discounts.py", type: "imports" },
  { id: "e2", source: "file:app/services/discounts.py", target: "file:app/models/discount.py", type: "reads" },
  { id: "e3", source: "file:tests/test_checkout.py", target: "file:app/api/checkout.py", type: "tests" },
  { id: "e4", source: "file:app/services/discounts.py", target: "file:app/core/config.py", type: "imports" },
];

function ArchitectureGraphPage() {
  const { data: graph } = useRepositoryGraph("demo-repo-id");
  const [selectedNode, setSelectedNode] = useState<string | null>("file:app/api/checkout.py");

  const nodes = graph?.nodes?.length ? graph.nodes : SEEDED_GRAPH_NODES;
  const edges = graph?.edges?.length ? graph.edges : SEEDED_GRAPH_EDGES;

  return (
    <div className="h-screen bg-canvas flex text-ink overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-full">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-semibold text-ink flex items-center gap-2">
                <GitFork className="w-5 h-5 text-accent" /> Repository Knowledge Graph
              </h1>
              <p className="text-xs text-ink-muted mt-1">
                Visualizing modules, symbol calls, database model dependencies, and test coverage blast radius
              </p>
            </div>
          </div>

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
                {/* Node Grid Layout */}
                <div className="w-full max-w-lg space-y-6">
                  {nodes.map((node) => {
                    const isSelected = selectedNode === node.id;
                    return (
                      <div
                        key={node.id}
                        onClick={() => setSelectedNode(node.id)}
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
                            </span>
                          </div>
                        </div>

                        {node.changed && <Badge variant="high">Modified in PR</Badge>}
                      </div>
                    );
                  })}
                </div>
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
                      <span className="font-mono text-xs text-accent font-semibold">
                        {selectedNode}
                      </span>
                    </div>

                    <div className="space-y-2">
                      <span className="text-xs font-semibold text-ink">
                        Outbound Imports / Reads:
                      </span>
                      <div className="p-2.5 rounded bg-canvas border border-line text-xs font-mono text-ink">
                        → app/services/discounts.py
                      </div>
                    </div>

                    <div className="space-y-2">
                      <span className="text-xs font-semibold text-ink">
                        Covering Test Suites:
                      </span>
                      <div className="p-2.5 rounded bg-success-soft border border-success-line text-xs font-mono text-success flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4" /> tests/test_checkout.py
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-ink-subtle">Click a node on the canvas to inspect blast radius.</p>
                )}
              </CardContent>
            </Card>
          </div>
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
