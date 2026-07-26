"use client";

import { useEffect, useState } from "react";
import DynamicEditor from "@monaco-editor/react";

interface DiffViewerProps {
  filePath: string;
  originalCode: string;
  suggestedCode?: string | null;
  highlightLine?: number;
}

export function DiffViewer({ filePath, originalCode, suggestedCode, highlightLine }: DiffViewerProps) {
  const [language, setLanguage] = useState("python");

  useEffect(() => {
    if (filePath.endsWith(".py")) setLanguage("python");
    else if (filePath.endsWith(".js") || filePath.endsWith(".jsx")) setLanguage("javascript");
    else if (filePath.endsWith(".ts") || filePath.endsWith(".tsx")) setLanguage("typescript");
    else if (filePath.endsWith(".json")) setLanguage("json");
    else setLanguage("plaintext");
  }, [filePath]);

  return (
    <div className="flex-1 flex flex-col h-full bg-slate-950 min-w-0 overflow-hidden">
      {/* File Header */}
      <div className="h-10 px-4 border-b border-slate-800 bg-slate-900/60 flex items-center justify-between font-mono text-xs text-slate-300">
        <span className="truncate">{filePath}</span>
        <div className="flex items-center space-x-2">
          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[10px]">
            {language}
          </span>
          {suggestedCode ? (
            <span className="text-emerald-400 text-[10px] bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">
              Diff Mode
            </span>
          ) : (
            <span className="text-slate-400 text-[10px]">Original Code</span>
          )}
        </div>
      </div>

      {/* Editor Container */}
      <div className="flex-1 relative min-h-0">
        {suggestedCode ? (
          <DynamicEditor
            height="100%"
            language={language}
            theme="vs-dark"
            original={originalCode}
            modified={suggestedCode}
            options={{
              readOnly: true,
              renderSideBySide: true,
              fontSize: 13,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              fontFamily: "'JetBrains Mono', monospace",
            }}
          />
        ) : (
          <DynamicEditor
            height="100%"
            language={language}
            theme="vs-dark"
            value={originalCode}
            options={{
              readOnly: true,
              fontSize: 13,
              minimap: { enabled: false },
              scrollBeyondLastLine: false,
              automaticLayout: true,
              fontFamily: "'JetBrains Mono', monospace",
              lineNumbers: "on",
            }}
          />
        )}
      </div>
    </div>
  );
}
