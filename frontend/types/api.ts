export type Severity = "critical" | "high" | "medium" | "low" | "informational";

export type FindingCategory =
  | "security"
  | "bug"
  | "performance"
  | "architecture"
  | "reliability"
  | "testing"
  | "code_quality"
  | "dependency"
  | "breaking_change"
  | "secret"
  | "prompt_injection";

export type FindingSource =
  | "ruff"
  | "bandit"
  | "mypy"
  | "semgrep"
  | "radon"
  | "eslint"
  | "tsc"
  | "npm_audit"
  | "trivy"
  | "gitleaks"
  | "osv"
  | "pytest"
  | "ast_rules"
  | "graph"
  | "ai_architecture"
  | "ai_security"
  | "ai_performance"
  | "ai_reliability"
  | "ai_testing"
  | "heuristic";

export type FindingStatus =
  | "open"
  | "fix_proposed"
  | "fix_approved"
  | "fix_rejected"
  | "resolved"
  | "ignored";

export type PatchStatus =
  | "proposed"
  | "validating"
  | "validated"
  | "validation_failed"
  | "approved"
  | "rejected"
  | "applied";

export type ValidationStatus = "pending" | "passed" | "failed" | "skipped";

export type RiskLevel = "critical" | "high" | "medium" | "low";

export type PullRequestStatus = "open" | "closed" | "merged";

export type AnalysisStatus = "queued" | "running" | "completed" | "failed" | "cancelled";

export interface User {
  id: string;
  github_user_id?: number | null;
  login?: string | null;
  name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
}

export interface GitHubInstallation {
  id: string;
  user_id: string;
  installation_id?: number | null;
  account_login?: string | null;
  account_type?: string | null;
  token_expires_at?: string | null;
  scopes?: string | null;
  created_at: string;
}

export interface RepositorySettings {
  id: string;
  repository_id: string;
  enabled_reviewers: string[];
  enabled_scanners: string[];
  severity_threshold: Severity;
  auto_scan_enabled: boolean;
  auto_apply_enabled: boolean;
  preferred_llm_provider?: string | null;
  preferred_llm_model?: string | null;
  max_analysis_cost: number;
  excluded_paths: string[];
  custom_rules: Record<string, any>[];
  notification_settings: Record<string, any>;
  data_retention_minutes: number;
}

export interface Repository {
  id: string;
  installation_id: string;
  github_repository_id: number;
  owner: string;
  name: string;
  full_name: string;
  description?: string | null;
  default_branch: string;
  primary_language?: string | null;
  languages: Record<string, number>;
  is_private: boolean;
  html_url?: string | null;
  clone_url?: string | null;
  stars: number;
  open_pr_count: number;
  last_analyzed_at?: string | null;
  created_at: string;
  updated_at: string;
  settings?: RepositorySettings | null;
}

export interface PullRequest {
  id: string;
  repository_id: string;
  github_pr_number: number;
  title: string;
  body?: string | null;
  base_ref: string;
  head_ref: string;
  base_sha: string;
  head_sha: string;
  author: string;
  author_avatar_url?: string | null;
  status: PullRequestStatus;
  is_draft: boolean;
  additions: number;
  deletions: number;
  changed_files: number;
  html_url?: string | null;
  created_at: string;
  updated_at: string;
  repository?: Repository | null;
  latest_analysis?: Analysis | null;
}

export interface AnalysisSummaryStats {
  total_findings: number;
  by_severity: Record<string, number>;
  by_category: Record<string, number>;
  by_source: Record<string, number>;
  patches_proposed: number;
  patches_validated: number;
  patches_approved: number;
  files_with_findings: number;
}

export interface Analysis {
  id: string;
  pull_request_id: string;
  status: AnalysisStatus;
  stage: string;
  progress: number;
  model_provider?: string | null;
  model_name?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  token_usage: number;
  estimated_cost: number;
  files_analyzed: number;
  scanners_run: string[];
  reviewers_run: string[];
  stage_timings: Record<string, number>;
  context_manifest: Record<string, any>;
  summary?: string | null;
  triggered_by: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_seconds?: number | null;
  error_message?: string | null;
  created_at: string;
  summary_stats?: AnalysisSummaryStats;
}

export interface Finding {
  id: string;
  analysis_id: string;
  category: FindingCategory;
  severity: Severity;
  confidence: number;
  score: number;
  title: string;
  description: string;
  risk: string;
  recommendation: string;
  file_path: string;
  start_line: number;
  end_line: number;
  code_snippet: string;
  source: FindingSource;
  corroborating_sources: string[];
  rule_id?: string | null;
  cwe?: string | null;
  fingerprint: string;
  status: FindingStatus;
  related_files: string[];
  score_breakdown: Record<string, number>;
  created_at: string;
  patches?: Patch[];
}

export interface ValidationRun {
  id: string;
  patch_id: string;
  parser_passed?: boolean | null;
  lint_passed?: boolean | null;
  typecheck_passed?: boolean | null;
  tests_passed?: boolean | null;
  security_scan_passed?: boolean | null;
  semantic_similarity: number;
  tests_before: Record<string, any>;
  tests_after: Record<string, any>;
  step_results: Array<{
    name: string;
    status: string;
    detail: string;
    duration: number;
  }>;
  test_output: string;
  skipped_reason?: string | null;
  execution_time: number;
  created_at: string;
}

export interface Patch {
  id: string;
  finding_id: string;
  file_path: string;
  original_code: string;
  suggested_code: string;
  unified_diff: string;
  explanation: string;
  expected_impact: string;
  side_effects: string[];
  confidence: number;
  confidence_breakdown: Record<string, number>;
  risk_level: RiskLevel;
  status: PatchStatus;
  validation_status: ValidationStatus;
  auto_apply_eligible: boolean;
  generated_by: string;
  approved_at?: string | null;
  approved_by?: string | null;
  rejected_at?: string | null;
  rejection_reason?: string | null;
  applied_commit_sha?: string | null;
  created_at: string;
  validation_runs?: ValidationRun[];
  finding?: Finding;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  file_path: string;
  language: string;
  start_line: number;
  end_line: number;
  changed: boolean;
  metrics: Record<string, any>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  weight: number;
}

export interface KnowledgeGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  metrics: {
    total_nodes: number;
    total_edges: number;
    changed_nodes: number;
  };
}

export interface AnalyticsSummary {
  findings_by_severity: Record<string, number>;
  findings_by_category: Record<string, number>;
  fix_acceptance_rate: number;
  average_analysis_duration: number;
  total_analyses_count: number;
  total_findings_count: number;
  top_risky_modules: Array<{ file_path: string; count: number }>;
}

export interface SSEProgressEvent {
  type: "started" | "progress" | "scanner" | "reviewer" | "findings" | "patch" | "completed" | "failed";
  analysis_id: string;
  timestamp: number;
  stage?: string;
  progress?: number;
  message?: string;
  count?: number;
  by_severity?: Record<string, number>;
  scanner?: string;
  reviewer?: string;
  ran?: boolean;
  patch_id?: string;
  finding_id?: string;
  file?: string;
  error?: string;
}
