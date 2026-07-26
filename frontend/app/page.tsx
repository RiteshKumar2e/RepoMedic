"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ShieldCheck,
  Zap,
  GitFork,
  Bug,
  TestTube,
  Lock,
  Sparkles,
  ArrowRight,
  CheckCircle2,
  Code2,
  FileCode2,
  Terminal,
  Cpu,
  Layers,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";

export default function LandingPage() {
  const { demoLogin, isLoggingIn } = useAuth();
  const router = useRouter();

  const handleDemoClick = async () => {
    await demoLogin();
    router.push("/dashboard");
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-sky-500/30">
      {/* Top Navbar */}
      <header className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <span className="font-bold text-slate-100 text-lg tracking-tight">RepoMedic</span>
              <span className="text-[10px] block font-mono text-sky-400">AI Code Reviewer & Auto-Fixer</span>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <button
              onClick={handleDemoClick}
              disabled={isLoggingIn}
              className="px-4 py-2 text-xs font-semibold bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded-lg transition-colors flex items-center gap-2"
            >
              <Sparkles className="w-4 h-4" />
              {isLoggingIn ? "Starting Demo..." : "Explore Demo Mode"}
            </button>
            <Link href="/dashboard">
              <Button size="default" className="gap-2">
                Open Workspace <ArrowRight className="w-4 h-4" />
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative pt-20 pb-16 px-6 max-w-7xl mx-auto text-center overflow-hidden">
        {/* Subtle background glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[300px] bg-sky-500/10 blur-[120px] rounded-full pointer-events-none" />

        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-xs font-medium text-sky-400 mb-6">
          <Sparkles className="w-3.5 h-3.5" />
          <span>Repository-Aware AI Code Review Platform</span>
        </div>

        <h1 className="text-4xl sm:text-6xl font-extrabold tracking-tight text-slate-100 max-w-4xl mx-auto leading-tight">
          Review deeper. Fix safer. <br />
          <span className="bg-gradient-to-r from-sky-400 via-teal-300 to-indigo-400 bg-clip-text text-transparent">
            Ship confidently.
          </span>
        </h1>

        <p className="mt-6 text-lg sm:text-xl text-slate-400 max-w-3xl mx-auto leading-relaxed">
          Repository-aware AI code review that detects architectural, security, performance, and reliability
          issues—and validates every proposed fix before it reaches your branch.
        </p>

        <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
          <Button size="lg" onClick={handleDemoClick} disabled={isLoggingIn} className="w-full sm:w-auto text-sm gap-2">
            <Sparkles className="w-4 h-4" /> Try Seeded Demo Mode
          </Button>
          <Link href="/dashboard" className="w-full sm:w-auto">
            <Button size="lg" variant="outline" className="w-full sm:w-auto text-sm gap-2">
              <Code2 className="w-4 h-4" /> View Live Dashboard
            </Button>
          </Link>
        </div>

        <div className="mt-8 flex items-center justify-center gap-6 text-xs text-slate-500">
          <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> AST Parsing</span>
          <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Knowledge Graph</span>
          <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> 6-Step Fix Validation</span>
          <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-emerald-400" /> Zero Hallucination Patches</span>
        </div>
      </section>

      {/* Live Diff Preview Section */}
      <section className="max-w-6xl mx-auto px-6 py-8">
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 shadow-2xl overflow-hidden glass-panel glow-blue">
          <div className="px-4 py-3 border-b border-slate-800 bg-slate-950 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <div className="w-3 h-3 rounded-full bg-red-500/80" />
              <div className="w-3 h-3 rounded-full bg-amber-500/80" />
              <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
              <span className="ml-2 text-xs font-mono text-slate-400">
                ecommerce-api-demo / app/api/checkout.py
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <Badge variant="critical">SQL Injection Detected</Badge>
              <Badge variant="success">Patch Validated (100%)</Badge>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-800 font-mono text-xs">
            {/* Original Vulnerable Code */}
            <div className="p-4 bg-slate-950/60 overflow-x-auto">
              <div className="text-[11px] font-sans font-semibold text-red-400 mb-2 flex items-center gap-1.5">
                <span>- Original Vulnerable Code</span>
              </div>
              <pre className="text-slate-300">
{`# Vulnerable to raw string SQL injection
@app.post("/discounts/apply")
async function apply_discount(code: str, db: Session):
    query = f"SELECT * FROM discounts WHERE code = '{code}'"
    result = db.execute(text(query)).fetchone()
    if not result:
        raise HTTPException(404, "Invalid code")
    return {"discount": result.amount}`}
              </pre>
            </div>

            {/* Proposed Validated Fix */}
            <div className="p-4 bg-emerald-950/20 overflow-x-auto">
              <div className="text-[11px] font-sans font-semibold text-emerald-400 mb-2 flex items-center gap-1.5">
                <span>+ Validated Safe Fix (AST + Typecheck + Tests Passed)</span>
              </div>
              <pre className="text-slate-200">
{`# Parameterized SQL execution prevents SQLi
@app.post("/discounts/apply")
async function apply_discount(code: str, db: Session):
    stmt = select(Discount).where(Discount.code == code)
    result = db.exec(stmt).first()
    if not result:
        raise HTTPException(404, "Invalid code")
    return {"discount": result.amount}`}
              </pre>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Highlights Grid */}
      <section className="max-w-7xl mx-auto px-6 py-16">
        <div className="text-center mb-12">
          <h2 className="text-2xl sm:text-3xl font-bold text-slate-100">
            Engineered for Deep Code Intelligence
          </h2>
          <p className="text-slate-400 text-sm mt-2">
            Not a basic wrapper or regex scanner. Multi-agent review backed by static analysis.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/50 hover:border-slate-700 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 mb-4">
              <GitFork className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-slate-100">Repository Knowledge Graph</h3>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Extracts symbols, functions, routes, database models, and imports. Analyzes unchanged files to catch cross-file breaking changes.
            </p>
          </div>

          <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/50 hover:border-slate-700 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 mb-4">
              <TestTube className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-slate-100">6-Step Fix Validation</h3>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Every patch is parsed, linted, type-checked, security-scanned, and tested before you review it. Zero broken code suggestions.
            </p>
          </div>

          <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/50 hover:border-slate-700 transition-colors">
            <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 mb-4">
              <Lock className="w-5 h-5" />
            </div>
            <h3 className="text-base font-semibold text-slate-100">AI Prompt-Injection Firewall</h3>
            <p className="text-xs text-slate-400 mt-2 leading-relaxed">
              Repository content is treated as untrusted data. Automatic secret redaction and hidden instruction detection keep your code safe.
            </p>
          </div>
        </div>
      </section>

      {/* Supported Languages */}
      <section className="max-w-7xl mx-auto px-6 py-12 border-t border-slate-800/80">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8">
          <div>
            <h3 className="text-lg font-semibold text-slate-100">Multi-Language Parsing & Adapters</h3>
            <p className="text-xs text-slate-400 mt-1">
              Tree-sitter AST analysis for Python, JavaScript, TypeScript, and TSX.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {["Python", "JavaScript", "TypeScript", "TSX", "JSON", "YAML"].map((lang) => (
              <span key={lang} className="px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono text-slate-300">
                {lang}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="mt-auto border-t border-slate-800/80 bg-slate-950 py-8 px-6 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center space-x-2">
            <ShieldCheck className="w-4 h-4 text-sky-400" />
            <span className="font-semibold text-slate-300">RepoMedic AI</span>
            <span>— Production-Ready Code Reviewer</span>
          </div>
          <p>MIT License © 2026 RepoMedic. Built for engineering teams.</p>
        </div>
      </footer>
    </div>
  );
}
