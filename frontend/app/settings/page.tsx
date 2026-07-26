"use client";

import { useState } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { Header } from "@/components/layout/Header";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Settings, Cpu, ShieldCheck, DollarSign, Save, Sliders, CheckCircle2 } from "lucide-react";

export default function SettingsPage() {
  const [provider, setProvider] = useState("anthropic");
  const [model, setModel] = useState("claude-sonnet-5");
  const [severityThreshold, setSeverityThreshold] = useState("low");
  const [maxCost, setMaxCost] = useState("2.00");
  const [saved, setSaved] = useState(false);

  const [agents, setAgents] = useState({
    architecture: true,
    security: true,
    performance: true,
    reliability: true,
    testing: true,
  });

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  };

  return (
    <div className="min-h-screen bg-slate-950 flex text-slate-100">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />

        <main className="flex-1 p-6 space-y-6 overflow-y-auto max-w-5xl">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-slate-100 flex items-center gap-2">
                <Settings className="w-5 h-5 text-sky-400" /> Platform & Review Settings
              </h1>
              <p className="text-xs text-slate-400 mt-1">
                Configure AI model providers, enabled scanners, cost budgets, and excluded file paths
              </p>
            </div>

            <Button onClick={handleSave} className="gap-2">
              <Save className="w-4 h-4" /> {saved ? "Settings Saved!" : "Save Settings"}
            </Button>
          </div>

          {/* AI Model Provider Configuration */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="w-4 h-4 text-sky-400" /> LLM Provider Abstraction
              </CardTitle>
              <CardDescription>Select primary model provider for contextual reasoning</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300">Default LLM Provider</label>
                  <select
                    value={provider}
                    onChange={(e) => setProvider(e.target.value)}
                    className="w-full h-9 px-3 bg-slate-900 border border-slate-800 rounded-md text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                  >
                    <option value="anthropic">Anthropic Claude (Recommended)</option>
                    <option value="openai">OpenAI (GPT-4o / O3)</option>
                    <option value="groq">Groq Llama-3 (Fast Inference)</option>
                    <option value="local">Local Ollama / vLLM</option>
                    <option value="heuristic">Offline Heuristic Engine (No API Key)</option>
                  </select>
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300">Model Name</label>
                  <input
                    type="text"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="w-full h-9 px-3 bg-slate-900 border border-slate-800 rounded-md text-xs text-slate-200 font-mono"
                  />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Reviewer Agents Toggle */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sliders className="w-4 h-4 text-amber-400" /> Specialized AI Reviewer Agents
              </CardTitle>
              <CardDescription>Enable or disable reviewer specialties</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              {Object.entries(agents).map(([agentKey, isEnabled]) => (
                <label
                  key={agentKey}
                  className="flex items-center justify-between p-3 rounded bg-slate-950 border border-slate-800 cursor-pointer hover:border-slate-700"
                >
                  <span className="font-semibold text-slate-200 capitalize">{agentKey} Reviewer</span>
                  <input
                    type="checkbox"
                    checked={isEnabled}
                    onChange={() => setAgents({ ...agents, [agentKey]: !isEnabled })}
                    className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-sky-500"
                  />
                </label>
              ))}
            </CardContent>
          </Card>

          {/* Token & Cost Budget */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <DollarSign className="w-4 h-4 text-emerald-400" /> Cost & Security Controls
              </CardTitle>
              <CardDescription>Per-analysis spending limits and auto-apply rules</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300">Max Cost Per Analysis (USD)</label>
                  <input
                    type="number"
                    step="0.5"
                    value={maxCost}
                    onChange={(e) => setMaxCost(e.target.value)}
                    className="w-full h-9 px-3 bg-slate-900 border border-slate-800 rounded-md text-xs text-slate-200 font-mono"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-300">Minimum Reporting Severity</label>
                  <select
                    value={severityThreshold}
                    onChange={(e) => setSeverityThreshold(e.target.value)}
                    className="w-full h-9 px-3 bg-slate-900 border border-slate-800 rounded-md text-xs text-slate-200 focus:outline-none focus:border-sky-500 font-mono"
                  >
                    <option value="critical">Critical Only</option>
                    <option value="high">High & Above</option>
                    <option value="medium">Medium & Above</option>
                    <option value="low">Low & Above (Recommended)</option>
                  </select>
                </div>
              </div>
            </CardContent>
          </Card>
        </main>
      </div>
    </div>
  );
}
