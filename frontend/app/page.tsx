"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Stethoscope } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

/* Four steps, in the order they actually run. This is the differentiator, so
   it is the only explanatory section on the page. */
const PIPELINE = [
  {
    step: "01",
    title: "Isolate",
    body: "The pull request is checked out into a disposable, size-capped sandbox with no network access. Repository source is never persisted and never runs on the host.",
  },
  {
    step: "02",
    title: "Parse",
    body: "Python through the stdlib AST, JavaScript and TypeScript through tree-sitter. Symbols, imports and calls become a graph that resolves what each change can reach.",
  },
  {
    step: "03",
    title: "Scan",
    body: "Ruff, Bandit, Mypy, ESLint, tsc, Semgrep, Gitleaks and OSV run before any model does. Their output is normalised into one schema and deduplicated.",
  },
  {
    step: "04",
    title: "Reason",
    body: "Retrieval selects the changed hunks plus graph-adjacent code — never the whole repository — and five specialist reviewers assess what deterministic tools cannot judge.",
  },
];

/* Plain factual statements. Anything that sounds like a promise is a claim the
   product has to keep, so each of these maps to real behaviour. */
const GUARANTEES = [
  [
    "Every patch is proven before you see it",
    "Applied in the sandbox, then re-parsed, linted, type-checked, security-scanned and tested against the baseline. Failures are attached to the patch rather than hidden.",
  ],
  [
    "Nothing lands without a human",
    "Auto-apply is off by default. Fixes only ever open a new branch — never a commit to your default branch.",
  ],
  [
    "Your code is untrusted input",
    "Secrets are redacted before a model sees anything, and instructions hidden in comments or READMEs are neutralised and reported as findings.",
  ],
  [
    "Nothing is retained",
    "Workspaces are deleted after the retention window. Only metadata, findings and small patch excerpts are stored.",
  ],
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
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-white">
              <Stethoscope className="h-4 w-4" strokeWidth={2.25} />
            </span>
            <span className="text-[15px] font-semibold tracking-tight">RepoMedic</span>
          </div>

          {/* Two actions, not three. The demo lives in the hero where it is
              the natural next step, not competing in the nav. */}
          <div className="flex items-center gap-2">
            <Link href="/login">
              <Button variant="ghost" size="sm">
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
        <section className="mx-auto max-w-5xl px-6 pb-14 pt-24">
          <h1 className="max-w-3xl text-[38px] font-semibold leading-[1.12] tracking-tight text-ink sm:text-[46px]">
            Code review that reads the whole repository.
          </h1>
          <p className="mt-5 max-w-2xl text-[16px] leading-relaxed text-ink-muted">
            RepoMedic finds the security, correctness and design defects a diff alone cannot show,
            writes a minimal patch, and proves that patch compiles, lints, type-checks and passes
            your tests — before anyone is asked to approve it.
          </p>

          <div className="mt-9 flex flex-wrap items-center gap-3">
            <Button variant="default" size="lg" onClick={handleDemoClick} disabled={isLoggingIn}>
              {isLoggingIn ? "Starting demo…" : "See it review a pull request"}
              <ArrowRight className="h-4 w-4" />
            </Button>
            <Link href="/register">
              <Button variant="secondary" size="lg">
                Create an account
              </Button>
            </Link>
          </div>

          <p className="mt-4 text-[13px] text-ink-subtle">
            The demo needs no account. It runs the real pipeline over a seeded, deliberately
            vulnerable repository.
          </p>
        </section>

        {/* ---------------------------------------------- the product artifact */}
        <section className="mx-auto max-w-5xl px-6 pb-24">
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
                  <p className="text-[13px] leading-relaxed text-ink-muted">
                    The value is passed as a bound parameter, so the driver sends it separately from
                    the statement and it can never be parsed as SQL. The query shape and result set
                    are identical — no side effects.
                  </p>
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

        {/* ----------------------------------------------------------- pipeline */}
        <section className="border-t border-line bg-surface">
          <div className="mx-auto max-w-5xl px-6 py-20">
            <p className="font-mono text-[11px] uppercase tracking-wider text-ink-subtle">
              How it works
            </p>
            <h2 className="mt-3 max-w-2xl text-[22px] font-semibold leading-snug tracking-tight text-ink">
              Deterministic analysis runs first and carries most of the weight.
            </h2>

            <ol className="mt-12 space-y-9">
              {PIPELINE.map((item) => (
                <li key={item.step} className="grid gap-x-6 gap-y-2 sm:grid-cols-[3rem_9rem_1fr]">
                  <span className="font-mono text-[13px] text-accent">{item.step}</span>
                  <h3 className="text-[15px] font-semibold text-ink">{item.title}</h3>
                  <p className="max-w-2xl text-[14px] leading-relaxed text-ink-muted">{item.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* --------------------------------------------------------- guarantees */}
        <section className="mx-auto max-w-5xl px-6 py-20">
          <p className="font-mono text-[11px] uppercase tracking-wider text-ink-subtle">
            What it guarantees
          </p>

          <div className="mt-10 grid gap-x-12 gap-y-9 sm:grid-cols-2">
            {GUARANTEES.map(([title, body]) => (
              <div key={title}>
                <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-ink-muted">{body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ---------------------------------------------------------------- cta */}
        <section className="border-t border-line bg-surface">
          <div className="mx-auto flex max-w-5xl flex-col items-start gap-6 px-6 py-16 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-[20px] font-semibold tracking-tight text-ink">
                See it review a real pull request.
              </h2>
              <p className="mt-1.5 text-[14px] text-ink-muted">
                Findings, patches, validation results and the dependency graph — no account needed.
              </p>
            </div>
            <Button
              variant="default"
              size="lg"
              onClick={handleDemoClick}
              disabled={isLoggingIn}
              className="shrink-0"
            >
              {isLoggingIn ? "Starting demo…" : "Open the demo workspace"}
              <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-3 px-6 py-6">
          <span className="text-[13px] text-ink-muted">
            Python, JavaScript and TypeScript today — Java, Go, Rust and C++ plug into the same
            analyzer interface.
          </span>
          <span className="font-mono text-xs text-ink-subtle">MIT licensed</span>
        </div>
      </footer>
    </div>
  );
}
