"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { GitFork, FileCode2, Layers, AlertTriangle, ArrowRight, ShieldCheck, Zap } from "lucide-react";
import { useRepositoryGraph } from "@/hooks/useGraph";

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

export default function ArchitectureGraphPage() {
  const { data: graph } = useRepositoryGraph("demo-repo-id");
  const [selectedNode, setSelectedNode] = useState<string | null>("file:app/api/checkout.py");

  const nodes = graph?.nodes?.length ? graph.nodes : SEEDED_GRAPH_NODES;
  const edges = graph?.edges?.length ? graph.edges : SEEDED_GRAPH_EDGES;

  return (
    <div className="h-screen bg-slate-950 flex text-slate-100 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-full">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
                <GitFork className="w-5 h-5 text-sky-400" /> Repository Knowledge Graph
              </h1>
              <p className="text-xs text-slate-400 mt-1">
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
                  5 Nodes • 4 Edges
                </Badge>
              </CardHeader>
              <CardContent className="flex-1 relative bg-slate-950/80 rounded-b-lg border-t border-slate-800 p-6 flex items-center justify-center">
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
                            ? "bg-sky-500/10 border-sky-500 text-sky-300 shadow-lg shadow-sky-500/10"
                            : node.changed
                            ? "bg-amber-500/10 border-amber-500/40 text-amber-200"
                            : "bg-slate-900 border-slate-800 text-slate-300 hover:border-slate-700"
                        }`}
                      >
                        <div className="flex items-center space-x-3">
                          <FileCode2 className="w-5 h-5 text-sky-400" />
                          <div>
                            <span className="font-mono text-xs font-semibold">{node.label}</span>
                            <span className="text-[10px] block text-slate-400 capitalize">
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
                    <div className="p-3 rounded bg-slate-950 border border-slate-800">
                      <span className="text-[11px] font-mono text-slate-400 block mb-1">
                        Selected Target
                      </span>
                      <span className="font-mono text-xs text-sky-400 font-semibold">
                        {selectedNode}
                      </span>
                    </div>

                    <div className="space-y-2">
                      <span className="text-xs font-semibold text-slate-300">
                        Outbound Imports / Reads:
                      </span>
                      <div className="p-2.5 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300">
                        → app/services/discounts.py
                      </div>
                    </div>

                    <div className="space-y-2">
                      <span className="text-xs font-semibold text-slate-300">
                        Covering Test Suites:
                      </span>
                      <div className="p-2.5 rounded bg-emerald-950/20 border border-emerald-900/30 text-xs font-mono text-emerald-400 flex items-center gap-2">
                        <ShieldCheck className="w-4 h-4" /> tests/test_checkout.py
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-xs text-slate-500">Click a node on the canvas to inspect blast radius.</p>
                )}
              </CardContent>
            </Card>
          </div>
        </main>
      </div>
    </div>
  );
}
