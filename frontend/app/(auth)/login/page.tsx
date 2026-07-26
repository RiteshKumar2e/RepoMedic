"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ShieldCheck, Github, Sparkles, Lock, CheckCircle2, ArrowRight } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/Card";
import { api } from "@/lib/api";

export default function LoginPage() {
  const { demoLogin, isLoggingIn } = useAuth();
  const router = useRouter();
  const [isGitHubConnecting, setIsGitHubConnecting] = useState(false);

  const handleDemoClick = async () => {
    await demoLogin();
    router.push("/dashboard");
  };

  const handleGitHubAuth = async () => {
    setIsGitHubConnecting(true);
    try {
      const res = await api.post<{ authorize_url: string; configured: boolean }>("/auth/github", {
        redirect_path: "/dashboard",
      });
      if (res.configured && res.authorize_url) {
        window.location.href = res.authorize_url;
      } else {
        // Fallback to demo mode if GitHub OAuth isn't configured in environment
        await demoLogin();
        router.push("/dashboard");
      }
    } catch {
      await demoLogin();
      router.push("/dashboard");
    } finally {
      setIsGitHubConnecting(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center p-6 relative">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 mx-auto mb-3">
            <ShieldCheck className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-bold text-slate-100">Welcome to RepoMedic</h1>
          <p className="text-xs text-slate-400 mt-1">Connect your account or explore seeded demo mode</p>
        </div>

        <Card className="border-slate-800 bg-slate-900/80 backdrop-blur-md shadow-2xl">
          <CardHeader className="text-center">
            <CardTitle>Authentication</CardTitle>
            <CardDescription>Minimum required permissions requested</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <Button
              onClick={handleGitHubAuth}
              disabled={isGitHubConnecting}
              className="w-full h-11 bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-700 flex items-center justify-center gap-2 text-sm"
            >
              <Github className="w-4 h-4" />
              {isGitHubConnecting ? "Connecting to GitHub..." : "Continue with GitHub"}
            </Button>

            <div className="relative my-4 text-center">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-slate-800" />
              </div>
              <span className="relative bg-slate-900 px-3 text-[11px] font-mono text-slate-500 uppercase">
                Or explore without login
              </span>
            </div>

            <Button
              onClick={handleDemoClick}
              disabled={isLoggingIn}
              variant="secondary"
              className="w-full h-11 bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 flex items-center justify-center gap-2 text-sm"
            >
              <Sparkles className="w-4 h-4" />
              {isLoggingIn ? "Preparing Demo Environment..." : "Explore Seeded Demo Mode"}
            </Button>
          </CardContent>

          <CardFooter className="flex flex-col items-start gap-2 bg-slate-950/40 text-[11px] text-slate-400">
            <div className="flex items-center gap-1.5 text-slate-400">
              <Lock className="w-3.5 h-3.5 text-emerald-400" />
              <span>Read-only code access. Secrets are redacted automatically.</span>
            </div>
            <div className="flex items-center gap-1.5 text-slate-400">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              <span>Full audit logging for all review actions and PR creations.</span>
            </div>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}
