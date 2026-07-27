"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Stethoscope } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

const DETECTS = [
  {
    group: "Security",
    items: [
      "SQL, command and template injection",
      "Authentication and authorization bypass",
      "SSRF, XSS, CSRF, path traversal",
      "Hardcoded secrets and weak cryptography",
    ],
  },
  {
    group: "Correctness & reliability",
    items: [
      "Swallowed exceptions and missing error handling",
      "Race conditions on shared mutable state",
      "Missing timeouts and retry problems",
      "Resource leaks and transaction gaps",
    ],
  },
  {
    group: "Performance & design",
    items: [
      "N+1 queries and unbounded pagination",
      "Blocking calls inside async handlers",
      "Layer violations and circular imports",
      "Duplicate logic and breaking API changes",
    ],
  },
];

const PIPELINE = [
  {
    step: "01",
    title: "Clone into an isolated workspace",
    body: "The pull request is checked out into a disposable, size-capped sandbox that is deleted when the analysis ends. Repository source is never persisted.",
  },
  {
    step: "02",
    title: "Parse, then build a graph",
    body: "Python is parsed with the stdlib AST; JavaScript and TypeScript with tree-sitter. Symbols, imports and calls become a knowledge graph that resolves what each change can break.",
  },
  {
    step: "03",
    title: "Run deterministic tools first",
    body: "Ruff, Bandit, Mypy, ESLint, tsc, Semgrep, Gitleaks and OSV run before any model does. Their findings are normalized into one schema and deduplicated.",
  },
  {
    step: "04",
    title: "Reason only over what matters",
    body: "Retrieval selects the changed hunks plus graph-adjacent code — never the whole repository — then five specialist reviewers assess architecture, security, performance, reliability and tests.",
  },
];

const VALIDATION_STEPS = [
  "Patched file re-parsed with the language's own AST",
  "Project linter run against the result",
  "Type checker run against the result",
  "Security scanner re-run to catch new weaknesses",
  "Relevant tests executed before and after, then compared",
];

export default function LandingPage() {
  const { demoLogin, isLoggingIn } = useAuth();
  const router = useRouter();
  const [tab, setTab] = useState<"finding" | "fix" | "validation">("finding");

  const handleDemoClick = async () => {
    await demoLogin();
    router.push("/dashboard");
  };

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      {/* ---------------------------------------------------------------- nav */}
      <header className="sticky top-0 z-50 border-b border-line bg-canvas/90 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-white">
              <Stethoscope className="h-4 w-4" strokeWidth={2.25} />
            </span>
            <span className="text-[15px] font-semibold tracking-tight">RepoMedic</span>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={handleDemoClick} disabled={isLoggingIn}>
              {isLoggingIn ? "Starting…" : "Try the demo"}
            </Button>
            <Link href="/login">
              <Button variant="secondary" size="sm">
                Sign in
              </Button>
            </Link>
            <Link href="/register">
              <Button variant="default" size="sm">
                Get started
              </Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* -------------------------------------------------------------- hero */}
        <section className="mx-auto max-w-6xl px-6 pb-16 pt-20">
          <div className="max-w-2xl">
            <p className="mb-4 font-mono text-xs tracking-wide text-ink-muted">
              Repository-aware code review
            </p>
            <h1 className="text-[40px] font-semibold leading-[1.1] tracking-tight text-ink sm:text-5xl">
              Review deeper.
              <br />
              Fix safer. Ship faster.
            </h1>
            <p className="mt-5 text-[15px] leading-relaxed text-ink-muted">
              RepoMedic reads a pull request the way a senior engineer does — against the rest of
              the repository. It finds architectural, security, performance and reliability defects,
              proposes a minimal patch, and validates that patch before anyone is asked to approve
              it.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button variant="default" size="lg" onClick={handleDemoClick} disabled={isLoggingIn}>
                {isLoggingIn ? "Starting demo…" : "Explore the demo"}
                <ArrowRight className="h-4 w-4" />
              </Button>
              <Link href="/register">
                <Button variant="secondary" size="lg">
                  Create an account
                </Button>
              </Link>
            </div>

            <p className="mt-4 text-xs text-ink-subtle">
              No account needed for the demo — it runs against a seeded fixture repository.
            </p>
          </div>
        </section>

        {/* ------------------------------------------------- diff preview panel */}
        <section className="mx-auto max-w-6xl px-6 pb-20">
          <div className="overflow-hidden rounded-lg border border-line">
            <div className="flex items-center justify-between border-b border-line bg-surface px-4 py-2.5">
              <div className="flex items-center gap-2 font-mono text-xs text-ink-muted">
                <span className="text-ink">app/routes/checkout.py</span>
                <span className="text-ink-subtle">·</span>
                <span>line 28</span>
              </div>
              <Badge variant="critical">Critical</Badge>
            </div>

            <div className="flex border-b border-line bg-surface px-2">
              {(
                [
                  ["finding", "Finding"],
                  ["fix", "Proposed fix"],
                  ["validation", "Validation"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={
                    tab === key
                      ? "-mb-px border-b-2 border-accent px-3 py-2 text-[13px] font-semibold text-ink"
                      : "-mb-px border-b-2 border-transparent px-3 py-2 text-[13px] text-ink-muted hover:text-ink"
                  }
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="bg-canvas p-4">
              {tab === "finding" && (
                <div className="space-y-4">
                  <pre className="overflow-x-auto rounded-md border border-line bg-surface p-3 font-mono text-[13px] leading-relaxed">
                    <code>
                      <span className="text-ink-subtle">26 </span>
                      {"    cursor = get_cursor()\n"}
                      <span className="text-ink-subtle">27 </span>
                      {"\n"}
                      <span className="bg-critical-soft">
                        <span className="text-ink-subtle">28 </span>
                        {'    cursor.execute(f"SELECT * FROM carts WHERE id = \'{cart_id}\'")\n'}
                      </span>
                      <span className="text-ink-subtle">29 </span>
                      {"    cart = cursor.fetchone()"}
                    </code>
                  </pre>
                  <div className="space-y-2 text-[13px] leading-relaxed">
                    <p className="font-semibold text-ink">
                      SQL injection: query built with string interpolation
                    </p>
                    <p className="text-ink-muted">
                      <code className="font-mono text-xs">cursor.execute()</code> receives a query
                      assembled with an f-string. Any value reaching this expression is concatenated
                      directly into SQL, so a caller controlling{" "}
                      <code className="font-mono text-xs">cart_id</code> controls the statement —
                      including appending <code className="font-mono text-xs">OR 1=1</code> or a
                      second statement entirely.
                    </p>
                    <p className="text-ink-muted">
                      <span className="font-medium text-ink">Risk.</span> Full read/write access to
                      the database, authentication bypass, and data exfiltration.
                    </p>
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      <Badge variant="neutral">CWE-89</Badge>
                      <Badge variant="neutral">ast_rules</Badge>
                      <Badge variant="neutral">bandit</Badge>
                      <Badge variant="neutral">semgrep</Badge>
                      <Badge variant="neutral">confidence 96%</Badge>
                    </div>
                  </div>
                </div>
              )}

              {tab === "fix" && (
                <div className="space-y-4">
                  <pre className="overflow-x-auto rounded-md border border-line bg-surface p-3 font-mono text-[13px] leading-relaxed">
                    <code>
                      <span className="block bg-critical-soft text-critical">
                        {
                          '-    cursor.execute(f"SELECT * FROM carts WHERE id = \'{cart_id}\'")'
                        }
                      </span>
                      <span className="block bg-success-soft text-success">
                        {'+    cursor.execute("SELECT * FROM carts WHERE id = %s", (cart_id,))'}
                      </span>
                    </code>
                  </pre>
                  <div className="space-y-2 text-[13px] leading-relaxed">
                    <p className="text-ink-muted">
                      The value is passed as a bound parameter, so the driver sends it separately
                      from the statement and it can never be parsed as SQL. Behaviour is otherwise
                      unchanged.
                    </p>
                    <p className="text-ink-muted">
                      <span className="font-medium text-ink">Side effects.</span> None — the query
                      shape and result set are identical.
                    </p>
                  </div>
                </div>
              )}

              {tab === "validation" && (
                <div className="space-y-3">
                  <ul className="divide-y divide-line-muted overflow-hidden rounded-md border border-line">
                    {[
                      ["Parse", "Patched file parses cleanly"],
                      ["Lint", "No new lint errors"],
                      ["Type check", "No type errors"],
                      ["Security scan", "No new security findings"],
                      ["Tests", "12 passed — unchanged from baseline"],
                    ].map(([name, detail]) => (
                      <li key={name} className="flex items-center gap-3 bg-canvas px-3 py-2">
                        <Check className="h-4 w-4 shrink-0 text-success" strokeWidth={2.5} />
                        <span className="w-28 shrink-0 text-[13px] font-medium text-ink">
                          {name}
                        </span>
                        <span className="text-[13px] text-ink-muted">{detail}</span>
                      </li>
                    ))}
                  </ul>
                  <p className="text-[13px] text-ink-muted">
                    Fix confidence <span className="font-semibold text-ink">92 / 100</span> · risk{" "}
                    <span className="font-medium text-ink">low</span> — still requires human
                    approval before it reaches a branch.
                  </p>
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ------------------------------------------------------------ detects */}
        <section className="border-t border-line bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <h2 className="text-xl font-semibold tracking-tight text-ink">What it finds</h2>
            <p className="mt-2 max-w-2xl text-[15px] text-ink-muted">
              Every finding names a file and line, explains the failure it causes, and carries a
              confidence score you can trace back to the tools that produced it.
            </p>

            <div className="mt-10 grid gap-10 sm:grid-cols-2 lg:grid-cols-3">
              {DETECTS.map((column) => (
                <div key={column.group}>
                  <h3 className="text-[13px] font-semibold uppercase tracking-wide text-ink-subtle">
                    {column.group}
                  </h3>
                  <ul className="mt-3 space-y-2">
                    {column.items.map((item) => (
                      <li key={item} className="text-[14px] leading-relaxed text-ink-muted">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ----------------------------------------------------------- pipeline */}
        <section className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="text-xl font-semibold tracking-tight text-ink">
            Why it isn&apos;t an LLM wrapper
          </h2>
          <p className="mt-2 max-w-2xl text-[15px] text-ink-muted">
            Deterministic analysis runs first and carries most of the weight. The model is used
            where judgement is genuinely needed — and never sees the whole repository.
          </p>

          <div className="mt-10 grid gap-px overflow-hidden rounded-lg border border-line bg-line sm:grid-cols-2">
            {PIPELINE.map((item) => (
              <div key={item.step} className="bg-canvas p-6">
                <span className="font-mono text-xs text-accent">{item.step}</span>
                <h3 className="mt-2 text-[15px] font-semibold text-ink">{item.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">{item.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* --------------------------------------------------------- validation */}
        <section className="border-t border-line bg-surface">
          <div className="mx-auto grid max-w-6xl gap-12 px-6 py-16 lg:grid-cols-2">
            <div>
              <h2 className="text-xl font-semibold tracking-tight text-ink">
                Every fix is proven before you see it
              </h2>
              <p className="mt-2 text-[15px] leading-relaxed text-ink-muted">
                A suggestion you have to verify yourself saves nothing. Each proposed patch is
                applied inside the sandbox and put through the same checks your CI would run. The
                result — including anything that failed — is attached to the patch.
              </p>
              <p className="mt-4 text-[15px] leading-relaxed text-ink-muted">
                Auto-apply is off by default. Fixes only ever land on a new branch, never on your
                default branch, and only after a human approves them.
              </p>
            </div>

            <ul className="space-y-3">
              {VALIDATION_STEPS.map((step) => (
                <li key={step} className="flex items-start gap-3">
                  <Check className="mt-0.5 h-4 w-4 shrink-0 text-success" strokeWidth={2.5} />
                  <span className="text-[14px] leading-relaxed text-ink-muted">{step}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* ----------------------------------------------------------- security */}
        <section className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="text-xl font-semibold tracking-tight text-ink">
            Your code is treated as untrusted input
          </h2>
          <div className="mt-8 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            {[
              [
                "Sandboxed execution",
                "Scanners and tests run in a network-disabled container with CPU, memory and process limits. Repository code never executes on the host.",
              ],
              [
                "Secrets never leave",
                "Every chunk is scanned and redacted before it reaches a model, and the analysis records exactly what was transmitted.",
              ],
              [
                "Prompt-injection firewall",
                "Instructions hidden in comments, README files, base64 or zero-width characters are neutralised and reported as findings.",
              ],
              [
                "Nothing is retained",
                "Workspaces are deleted after the retention window. Only metadata, findings and small patch excerpts are stored.",
              ],
            ].map(([title, body]) => (
              <div key={title}>
                <h3 className="text-[14px] font-semibold text-ink">{title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ---------------------------------------------------------- languages */}
        <section className="border-t border-line">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-3 px-6 py-8">
            <span className="text-[13px] font-semibold text-ink">Supported today</span>
            {["Python", "JavaScript", "TypeScript"].map((lang) => (
              <span key={lang} className="text-[13px] text-ink-muted">
                {lang}
              </span>
            ))}
            <span className="text-[13px] text-ink-subtle">
              Java, Go, Rust and C++ plug into the same analyzer interface.
            </span>
          </div>
        </section>

        {/* ---------------------------------------------------------------- cta */}
        <section className="border-t border-line bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-16 text-center">
            <h2 className="text-2xl font-semibold tracking-tight text-ink">
              See it review a real pull request
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-[15px] text-ink-muted">
              The demo workspace runs the full pipeline over a deliberately vulnerable repository —
              findings, patches, validation results and the dependency graph included.
            </p>
            <div className="mt-7 flex justify-center">
              <Button variant="default" size="lg" onClick={handleDemoClick} disabled={isLoggingIn}>
                {isLoggingIn ? "Starting demo…" : "Open the demo workspace"}
                <ArrowRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-6">
          <span className="text-[13px] text-ink-muted">
            RepoMedic — diagnose code, repair faster, ship confidently.
          </span>
          <span className="font-mono text-xs text-ink-subtle">MIT licensed</span>
        </div>
      </footer>
    </div>
  );
}
