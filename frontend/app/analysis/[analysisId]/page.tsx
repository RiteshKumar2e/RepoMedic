"use client";

import { use, useState, useMemo } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { FileTree } from "@/components/code-review/FileTree";
import { DiffViewer } from "@/components/code-review/DiffViewer";
import { FindingPanel } from "@/components/code-review/FindingPanel";
import { FilterBar } from "@/components/code-review/FilterBar";
import { AnalysisProgress } from "@/components/code-review/AnalysisProgress";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useAnalysis } from "@/hooks/useAnalysis";
import { useFindings } from "@/hooks/useFindings";
import { usePatchActions } from "@/hooks/usePatches";
import { Github, CheckCircle2, Sparkles, Send } from "lucide-react";
import type { Finding, Severity } from "@/types/api";

// Seeded fixture data for demo workspace if API query is pending/demo
const SEEDED_FILES = [
  { path: "app/api/checkout.py", status: "modified" },
  { path: "app/services/discounts.py", status: "modified" },
  { path: "tests/test_checkout.py", status: "modified" },
];

const SEEDED_FINDINGS: Finding[] = [
  {
    id: "f-1",
    analysis_id: "demo-analysis-id",
    category: "security",
    severity: "critical",
    confidence: 0.95,
    score: 95,
    title: "SQL Injection vulnerability in discount lookup",
    description: "Raw string interpolation inside SQL statement allows unauthorized database query execution.",
    risk: "Attackers can bypass authentication and read sensitive user data.",
    recommendation: "Use SQLAlchemy select() statement with bound parameters.",
    file_path: "app/api/checkout.py",
    start_line: 14,
    end_line: 22,
    code_snippet: 'query = f"SELECT * FROM discounts WHERE code = \'{code}\'"',
    source: "bandit",
    corroborating_sources: ["ai_security", "ast_rules"],
    fingerprint: "fp-sqli-checkout",
    status: "fix_proposed",
    related_files: [],
    score_breakdown: {},
    created_at: new Date().toISOString(),
    patches: [
      {
        id: "patch-1",
        finding_id: "f-1",
        file_path: "app/api/checkout.py",
        original_code: `@app.post("/discounts/apply")\nasync function apply_discount(code: str, db: Session):\n    query = f"SELECT * FROM discounts WHERE code = '{code}'"\n    result = db.execute(text(query)).fetchone()\n    if not result:\n        raise HTTPException(404, "Invalid code")\n    return {"discount": result.amount}`,
        suggested_code: `@app.post("/discounts/apply")\nasync function apply_discount(code: str, db: Session):\n    stmt = select(Discount).where(Discount.code == code)\n    result = db.exec(stmt).first()\n    if not result:\n        raise HTTPException(404, "Invalid code")\n    return {"discount": result.amount}`,
        unified_diff: "@@ -14,7 +14,7 @@\n-    query = f\"SELECT * FROM discounts WHERE code = '{code}'\"\n-    result = db.execute(text(query)).fetchone()\n+    stmt = select(Discount).where(Discount.code == code)\n+    result = db.exec(stmt).first()",
        explanation: "Replaced raw string query with parameterized SQLModel select statement.",
        expected_impact: "Eliminates SQL injection risk completely.",
        side_effects: [],
        confidence: 0.98,
        confidence_breakdown: {},
        risk_level: "low",
        status: "validated",
        validation_status: "passed",
        auto_apply_eligible: true,
        generated_by: "fix_generator",
        created_at: new Date().toISOString(),
      },
    ],
  },
  {
    id: "f-2",
    analysis_id: "demo-analysis-id",
    category: "security",
    severity: "high",
    confidence: 0.9,
    score: 90,
    title: "Hardcoded API Key secret in discounts service",
    description: "Hardcoded third-party provider secret key detected in source code.",
    risk: "Exposes credentials if repository is pushed to public remotes.",
    recommendation: "Load API key from environment variables via Settings.",
    file_path: "app/services/discounts.py",
    start_line: 8,
    end_line: 12,
    code_snippet: 'API_SECRET = "sk_live_99485720491823"',
    source: "gitleaks",
    corroborating_sources: ["ai_security"],
    fingerprint: "fp-secret-discounts",
    status: "fix_proposed",
    related_files: [],
    score_breakdown: {},
    created_at: new Date().toISOString(),
    patches: [
      {
        id: "patch-2",
        finding_id: "f-2",
        file_path: "app/services/discounts.py",
        original_code: `API_SECRET = "sk_live_99485720491823"`,
        suggested_code: `API_SECRET = settings.discount_api_key`,
        unified_diff: `-API_SECRET = "sk_live_99485720491823"\n+API_SECRET = settings.discount_api_key`,
        explanation: "Replaced hardcoded string with environment settings lookup.",
        expected_impact: "Secures credentials against exfiltration.",
        side_effects: [],
        confidence: 0.95,
        confidence_breakdown: {},
        risk_level: "low",
        status: "validated",
        validation_status: "passed",
        auto_apply_eligible: true,
        generated_by: "fix_generator",
        created_at: new Date().toISOString(),
      },
    ],
  },
];

export default function AnalysisPage({ params }: { params: Promise<{ analysisId: string }> }) {
  const resolvedParams = use(params);
  const analysisId = resolvedParams.analysisId;

  const { analysis, liveEvent } = useAnalysis(analysisId);
  const { data: rawFindings } = useFindings(analysisId);
  const { approvePatch, rejectPatch, publishReview, createFixPR, isApproving, isRejecting, isPublishing, isCreatingPR } =
    usePatchActions(analysisId);

  const findingsList = rawFindings?.length ? rawFindings : SEEDED_FINDINGS;

  const [selectedFile, setSelectedFile] = useState<string>("app/api/checkout.py");
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(SEEDED_FINDINGS[0]);
  const [selectedSeverities, setSelectedSeverities] = useState<Severity[]>([
    "critical",
    "high",
    "medium",
    "low",
    "informational",
  ]);
  const [searchQuery, setSearchQuery] = useState("");

  const filteredFindings = useMemo(() => {
    return findingsList.filter((f) => {
      const matchesSev = selectedSeverities.includes(f.severity);
      const matchesSearch =
        !searchQuery ||
        f.file_path.toLowerCase().includes(searchQuery.toLowerCase()) ||
        f.title.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesSev && matchesSearch;
    });
  }, [findingsList, selectedSeverities, searchQuery]);

  const handleToggleSeverity = (sev: Severity) => {
    if (selectedSeverities.includes(sev)) {
      setSelectedSeverities(selectedSeverities.filter((s) => s !== sev));
    } else {
      setSelectedSeverities([...selectedSeverities, sev]);
    }
  };

  const handleSelectFinding = (finding: Finding) => {
    setSelectedFinding(finding);
    setSelectedFile(finding.file_path);
  };

  return (
    <div className="h-screen bg-slate-950 flex text-slate-100 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 h-full">
        <Header />

        {/* Live SSE Progress Header */}
        <AnalysisProgress
          stage={analysis?.stage || "completed"}
          progress={analysis?.progress ?? 100}
          message={analysis?.summary || "Analysis completed. Review findings and approved patches below."}
          liveEvent={liveEvent}
        />

        {/* Action & Filter Toolbar */}
        <div className="flex flex-wrap items-center justify-between px-4 border-b border-slate-800 bg-slate-950/80">
          <FilterBar
            selectedSeverities={selectedSeverities}
            onToggleSeverity={handleToggleSeverity}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            totalCount={filteredFindings.length}
          />

          <div className="flex items-center space-x-2 py-2">
            <Button
              size="sm"
              variant="outline"
              disabled={isPublishing}
              onClick={() => publishReview(analysisId)}
              className="gap-1.5 text-xs"
            >
              <Send className="w-3.5 h-3.5" /> Publish Review Comment
            </Button>
            <Button
              size="sm"
              disabled={isCreatingPR}
              onClick={() => createFixPR({ id: analysisId })}
              className="gap-1.5 text-xs"
            >
              <Github className="w-3.5 h-3.5" /> Create Fix Pull Request
            </Button>
          </div>
        </div>

        {/* Main 3-Panel Code Review Workspace */}
        <div className="flex-1 flex min-h-0 overflow-hidden">
          {/* Left Panel: Changed File Tree */}
          <FileTree
            files={SEEDED_FILES}
            selectedFile={selectedFile}
            onSelectFile={(path) => setSelectedFile(path)}
            findings={filteredFindings}
          />

          {/* Center Panel: Monaco Side-By-Side Diff Editor */}
          <DiffViewer
            filePath={selectedFile}
            originalCode={
              selectedFinding?.patches?.[0]?.original_code ||
              `# Original code for ${selectedFile}\n@app.post("/discounts/apply")\nasync function apply_discount(code: str, db: Session):\n    query = f"SELECT * FROM discounts WHERE code = '{code}'"\n    return db.execute(text(query)).fetchone()`
            }
            suggestedCode={selectedFinding?.patches?.[0]?.suggested_code}
            highlightLine={selectedFinding?.start_line}
          />

          {/* Right Panel: AI Findings & Fix Review Cards */}
          <FindingPanel
            findings={filteredFindings}
            onSelectFinding={handleSelectFinding}
            onApprovePatch={(id) => approvePatch(id)}
            onRejectPatch={(id) => rejectPatch({ patchId: id })}
            isApproving={isApproving}
            isRejecting={isRejecting}
          />
        </div>
      </div>
    </div>
  );
}
