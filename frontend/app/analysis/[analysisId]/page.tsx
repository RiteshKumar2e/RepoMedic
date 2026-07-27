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

import { useAnalysis } from "@/hooks/useAnalysis";
import { useFindings } from "@/hooks/useFindings";
import { usePatchActions } from "@/hooks/usePatches";
import { Github, Send } from "lucide-react";
import type { Finding, Severity } from "@/types/api";
import { RequireAuth } from "@/components/auth/RequireAuth";

function AnalysisPage({ params }: { params: Promise<{ analysisId: string }> }) {
  const resolvedParams = use(params);
  const analysisId = resolvedParams.analysisId;

  const { analysis, liveEvent } = useAnalysis(analysisId);
  const { data: rawFindings } = useFindings(analysisId);
  const { approvePatch, rejectPatch, publishReview, createFixPR, isApproving, isRejecting, isPublishing, isCreatingPR } =
    usePatchActions(analysisId);

  // Real findings only. This used to fall back to a hardcoded fixture, so a
  // missing or 404'd analysis silently rendered invented vulnerabilities.
  const findingsList = useMemo(() => rawFindings ?? [], [rawFindings]);

  const [pickedFile, setPickedFile] = useState<string | null>(null);
  const [pickedFinding, setPickedFinding] = useState<string | null>(null);
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

  // The changed-file list is derived from the findings themselves, so it always
  // matches what the analysis actually reported.
  const files = useMemo(
    () =>
      Array.from(new Set(findingsList.map((f) => f.file_path)))
        .sort()
        .map((path) => ({ path })),
    [findingsList],
  );

  // Selections are derived so they can never point at a stale finding or file.
  const selectedFinding =
    findingsList.find((f) => f.id === pickedFinding) ?? filteredFindings[0] ?? null;
  const selectedFile = pickedFile ?? selectedFinding?.file_path ?? files[0]?.path ?? "";

  const handleToggleSeverity = (sev: Severity) => {
    if (selectedSeverities.includes(sev)) {
      setSelectedSeverities(selectedSeverities.filter((s) => s !== sev));
    } else {
      setSelectedSeverities([...selectedSeverities, sev]);
    }
  };

  const handleSelectFinding = (finding: Finding) => {
    setPickedFinding(finding.id);
    setPickedFile(finding.file_path);
  };

  return (
    <div className="h-screen bg-canvas flex text-ink overflow-hidden">
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
        <div className="flex flex-wrap items-center justify-between px-4 border-b border-line bg-canvas">
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
            files={files}
            selectedFile={selectedFile}
            onSelectFile={(path) => setPickedFile(path)}
            findings={filteredFindings}
          />

          {/* Center Panel: Monaco Side-By-Side Diff Editor */}
          <DiffViewer
            filePath={selectedFile}
            originalCode={
              selectedFinding?.patches?.[0]?.original_code ??
              selectedFinding?.code_snippet ??
              ""
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

export default function AnalysisPageRoute(props: Parameters<typeof AnalysisPage>[0]) {
  return (
    <RequireAuth>
      <AnalysisPage {...props} />
    </RequireAuth>
  );
}
