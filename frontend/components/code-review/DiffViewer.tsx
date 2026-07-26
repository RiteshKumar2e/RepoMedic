"use client";

import { useCallback, useMemo } from "react";
import Editor, { DiffEditor, type OnMount } from "@monaco-editor/react";

interface DiffViewerProps {
  filePath: string;
  originalCode: string;
  suggestedCode?: string | null;
  /** 1-based line to scroll to and highlight (the finding's location). */
  highlightLine?: number;
}

const EDITOR_FONT = "'JetBrains Mono', 'Fira Code', ui-monospace, monospace";

function languageFor(filePath: string): string {
  const path = filePath.toLowerCase();
  if (path.endsWith(".py") || path.endsWith(".pyi")) return "python";
  if (path.endsWith(".ts") || path.endsWith(".mts") || path.endsWith(".cts")) return "typescript";
  if (path.endsWith(".tsx")) return "typescript";
  if (path.endsWith(".js") || path.endsWith(".jsx") || path.endsWith(".mjs") || path.endsWith(".cjs"))
    return "javascript";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".yml") || path.endsWith(".yaml")) return "yaml";
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".html")) return "html";
  if (path.endsWith(".sql")) return "sql";
  return "plaintext";
}

export function DiffViewer({
  filePath,
  originalCode,
  suggestedCode,
  highlightLine,
}: DiffViewerProps) {
  // Derived from the path — no effect or state needed.
  const language = useMemo(() => languageFor(filePath), [filePath]);
  const isDiff = Boolean(suggestedCode);

  const handleMount = useCallback<OnMount>(
    (editor, monaco) => {
      if (!highlightLine || highlightLine < 1) return;

      editor.revealLineInCenter(highlightLine);
      editor.createDecorationsCollection([
        {
          range: new monaco.Range(highlightLine, 1, highlightLine, 1),
          options: {
            isWholeLine: true,
            className: "repomedic-highlight-line",
            linesDecorationsClassName: "repomedic-highlight-gutter",
          },
        },
      ]);
    },
    [highlightLine],
  );

  const sharedOptions = {
    readOnly: true,
    fontSize: 13,
    minimap: { enabled: false },
    scrollBeyondLastLine: false,
    automaticLayout: true,
    fontFamily: EDITOR_FONT,
    renderLineHighlight: "none",
    scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10 },
  } as const;

  return (
    <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden bg-canvas">
      <div className="flex h-10 items-center justify-between border-b border-line bg-surface px-4 font-mono text-xs text-ink">
        <span className="truncate" title={filePath}>
          {filePath}
        </span>
        <div className="flex shrink-0 items-center space-x-2">
          <span className="rounded bg-inset px-2 py-0.5 text-[10px] text-ink-muted">
            {language}
          </span>
          {isDiff ? (
            <span className="text-emerald-400 text-[10px] bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">
              Proposed fix
            </span>
          ) : (
            <span className="text-slate-400 text-[10px]">Original</span>
          )}
        </div>
      </div>

      <div className="flex-1 relative min-h-0">
        {isDiff ? (
          <DiffEditor
            height="100%"
            language={language}
            theme="vs-dark"
            original={originalCode}
            modified={suggestedCode ?? ""}
            options={{
              ...sharedOptions,
              // Diff-editor-only options live on IDiffEditorConstructionOptions.
              renderSideBySide: true,
              ignoreTrimWhitespace: false,
              renderOverviewRuler: false,
            }}
          />
        ) : (
          <Editor
            height="100%"
            language={language}
            theme="vs-dark"
            value={originalCode}
            onMount={handleMount}
            options={{ ...sharedOptions, lineNumbers: "on" }}
          />
        )}
      </div>
    </div>
  );
}
