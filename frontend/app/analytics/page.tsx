"use client";

import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { BarChart3, TrendingUp, ShieldAlert, CheckCircle2, Clock } from "lucide-react";
import { useAnalytics } from "@/hooks/useAnalytics";

export default function AnalyticsPage() {
  const { data: analytics } = useAnalytics();

  const categories = [
    { name: "Security & Secrets", count: 3, percent: 43, color: "bg-critical" },
    { name: "Performance (N+1, Async)", count: 2, percent: 29, color: "bg-medium" },
    { name: "Architecture & Cycles", count: 1, percent: 14, color: "bg-accent" },
    { name: "Missing Tests", count: 1, percent: 14, color: "bg-indigo-500" },
  ];

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
                <div className="text-3xl font-extrabold text-success">100%</div>
                <p className="text-xs text-ink-muted">3 of 3 proposed patches approved and merged</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Average Review Duration</CardTitle>
                <CardDescription>Full pipeline execution time</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="text-3xl font-extrabold text-accent">4.2s</div>
                <p className="text-xs text-ink-muted">Deterministic scans + AST + Parallel AI agents</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Total Findings Analyzed</CardTitle>
                <CardDescription>Across all open pull requests</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="text-3xl font-extrabold text-ink">7</div>
                <p className="text-xs text-ink-muted">1 Critical, 2 High, 3 Medium, 1 Low</p>
              </CardContent>
            </Card>
          </div>

          {/* Category Distribution */}
          <Card>
            <CardHeader>
              <CardTitle>Issues by Category</CardTitle>
              <CardDescription>Breakdown of detected problems</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {categories.map((cat) => (
                <div key={cat.name} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-ink font-medium">{cat.name}</span>
                    <span className="font-mono text-ink-muted">
                      {cat.count} ({cat.percent}%)
                    </span>
                  </div>
                  <div className="w-full bg-inset rounded-full h-2 overflow-hidden">
                    <div className={`h-full ${cat.color}`} style={{ width: `${cat.percent}%` }} />
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
