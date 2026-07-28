/**
 * Free-form JSON the API stores in a column and does not promise a shape for
 * (metrics, manifests, tool output). Narrow it at the point of use rather than
 * reaching for `any`.
 */
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export type JsonObject = Record<string, JsonValue>;

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
  custom_rules: JsonObject[];
  notification_settings: JsonObject;
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
}

/** GET /pull-requests/{id} — adds the fields only the detail route returns. */
export interface PullRequestDetail extends PullRequest {
  repository?: Repository | null;
  latest_analysis_id?: string | null;
  analysis_count: number;
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
  context_manifest: JsonObject;
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
  tests_before: JsonObject;
  tests_after: JsonObject;
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

/* Mirrors backend/app/schemas/graph.py. Most node fields are nullable there,
   so they are optional here — the previous shape claimed a `metrics` object the
   API never sends. */

export type GraphNodeType =
  | "file"
  | "module"
  | "class"
  | "function"
  | "route"
  | "model"
  | "test"
  | "dependency";

export interface GraphNode {
  id: string;
  label: string;
  type: GraphNodeType | string;
  file_path?: string | null;
  language?: string | null;
  start_line?: number | null;
  end_line?: number | null;
  finding_count: number;
  max_severity?: Severity | null;
  changed: boolean;
  metrics: JsonObject;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  weight: number;
}

/** GET /repositories/{id}/graph */
export interface KnowledgeGraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  generated_at?: string | null;
  truncated: boolean;
  stats: Record<string, number>;
}

/* The shapes below mirror backend/app/schemas/analytics.py exactly. They used
   to drift (`total_findings_count`, `average_analysis_duration`), which made
   every field resolve to undefined and silently fall back to placeholders. */

export interface SeverityCount {
  severity: Severity;
  count: number;
}

export interface CategoryCount {
  category: string;
  count: number;
}

export interface TrendPoint {
  date: string;
  critical: number;
  high: number;
  medium: number;
  low: number;
  informational: number;
  total: number;
}

export interface RiskyModule {
  file_path: string;
  finding_count: number;
  max_severity: Severity;
  score: number;
}

export interface ActivityItem {
  id: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  summary: string;
  created_at: string;
}

/** GET /dashboard */
export interface DashboardSummary {
  repository_count: number;
  open_pull_requests: number;
  active_analyses: number;
  total_findings: number;
  findings_by_severity: SeverityCount[];
  fix_acceptance_rate: number;
  average_review_seconds: number;
  patches_pending_review: number;
  recent_activity: ActivityItem[];
  trend: TrendPoint[];
}

/** GET /repositories/{id}/analytics */
export interface RepositoryAnalytics {
  repository_id: string;
  analyses_run: number;
  total_findings: number;
  findings_by_severity: SeverityCount[];
  findings_by_category: CategoryCount[];
  findings_by_source: CategoryCount[];
  fix_acceptance_rate: number;
  average_review_seconds: number;
  defect_trend: TrendPoint[];
  riskiest_modules: RiskyModule[];
  security_posture_score: number;
  language_distribution: Record<string, number>;
  total_estimated_cost: number;
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

/* ---------------------------------------------------------------------------
   Admin — mirrors backend/app/schemas/admin.py. Metadata only: the API never
   returns repository source, tokens or password hashes here.
   ------------------------------------------------------------------------- */

export interface AdminTotals {
  users: number;
  repositories: number;
  analyses: number;
  findings: number;
  patches: number;
  pull_requests: number;
}

export type AuthMethod = "github" | "password" | "none" | "unknown";

export interface AdminUserRow {
  id: string;
  login?: string | null;
  name?: string | null;
  email?: string | null;
  avatar_url?: string | null;
  auth_method: AuthMethod;
  github_connected: boolean;
  repository_count: number;
  analysis_count: number;
  is_admin: boolean;
  created_at: string;
}

export interface AdminRepositoryRow {
  id: string;
  full_name: string;
  owner_login?: string | null;
  owner_email?: string | null;
  primary_language?: string | null;
  is_private: boolean;
  open_pr_count: number;
  analysis_count: number;
  finding_count: number;
  last_analyzed_at?: string | null;
  created_at: string;
}

export interface AdminAnalysisRow {
  id: string;
  repository_full_name?: string | null;
  pull_request_number?: number | null;
  status: AnalysisStatus;
  stage: string;
  triggered_by: string;
  finding_count: number;
  duration_seconds?: number | null;
  estimated_cost: number;
  created_at: string;
}

export interface AdminFindingStats {
  total: number;
  by_severity: SeverityCount[];
  by_category: CategoryCount[];
  patches_proposed: number;
  patches_approved: number;
  patches_rejected: number;
  fix_acceptance_rate: number;
}

export interface AdminAuditRow {
  id: string;
  action: string;
  entity_type: string;
  entity_id?: string | null;
  actor_login?: string | null;
  actor_email?: string | null;
  ip_address?: string | null;
  created_at: string;
}

export interface AdminOverview {
  totals: AdminTotals;
  users: AdminUserRow[];
  repositories: AdminRepositoryRow[];
  analyses: AdminAnalysisRow[];
  findings: AdminFindingStats;
  audit: AdminAuditRow[];
}
