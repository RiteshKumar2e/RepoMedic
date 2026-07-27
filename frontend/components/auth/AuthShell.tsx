import Link from "next/link";
import { Check, Stethoscope } from "lucide-react";

const PROOF_POINTS = [
  {
    title: "Deterministic scanners run first",
    body: "Ruff, Bandit, Mypy, ESLint, Semgrep, Gitleaks and OSV — before a model sees anything.",
  },
  {
    title: "Every patch is validated",
    body: "Parsed, linted, type-checked and tested in a sandbox before a human is asked to approve it.",
  },
  {
    title: "Your code stays yours",
    body: "Only the relevant chunks are retrieved, secrets are redacted, and writes are gated.",
  },
];

/**
 * Two-column frame for sign in and sign up: the form on the left where the eye
 * lands first, supporting evidence on the right. The right column is hidden
 * below `lg` so small screens get the form alone rather than a squeezed pair.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="grid min-h-screen bg-canvas lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      {/* Form column */}
      <div className="flex flex-col px-6 py-10 sm:px-10">
        <Link href="/" className="mb-auto inline-flex items-center gap-2.5 self-start">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-accent text-white">
            <Stethoscope className="h-4 w-4" strokeWidth={2.25} />
          </span>
          <span className="text-[15px] font-semibold tracking-tight text-ink">RepoMedic</span>
        </Link>

        <main className="mx-auto w-full max-w-sm py-12">
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">{title}</h1>
          <p className="mt-1.5 text-[13px] text-ink-muted">{subtitle}</p>
          <div className="mt-7">{children}</div>
        </main>

        <div className="mt-auto text-[12px] text-ink-subtle">{footer}</div>
      </div>

      {/* Evidence column */}
      <aside className="hidden border-l border-line bg-surface px-10 py-10 lg:flex lg:flex-col lg:justify-center">
        <div className="max-w-md">
          <p className="font-mono text-[11px] uppercase tracking-wider text-ink-subtle">
            Why teams trust the review
          </p>
          <h2 className="mt-3 text-lg font-semibold leading-snug tracking-tight text-ink">
            Diagnose code. Repair faster. Ship confidently.
          </h2>

          <ul className="mt-7 space-y-5">
            {PROOF_POINTS.map((point) => (
              <li key={point.title} className="flex gap-3">
                <span className="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-success-soft text-success">
                  <Check className="h-3 w-3" strokeWidth={3} />
                </span>
                <div>
                  <p className="text-[13px] font-medium text-ink">{point.title}</p>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-ink-muted">{point.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </div>
  );
}
