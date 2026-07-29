"use client";

import { useMemo, useRef, useState } from "react";
import { layoutGraph, type LaidOutNode } from "./forceLayout";
import type { GraphEdge, GraphNode, Severity } from "@/types/api";
import { cn } from "@/lib/utils";

const WIDTH = 1000;
const HEIGHT = 620;

/** Beyond this the layout is slow and the picture is an unreadable hairball. */
const MAX_RENDERED = 70;

/* Node fill follows the same meaning as everywhere else in the product:
   colour is severity, never decoration. A node with no findings is neutral. */
const SEVERITY_FILL: Record<Severity, { fill: string; ring: string }> = {
  critical: { fill: "var(--critical)", ring: "var(--critical-line)" },
  high: { fill: "var(--high)", ring: "var(--high-line)" },
  medium: { fill: "var(--medium)", ring: "var(--medium-line)" },
  low: { fill: "var(--low)", ring: "var(--low-line)" },
  informational: { fill: "var(--info)", ring: "var(--info-line)" },
};

const CLEAN = { fill: "var(--success)", ring: "var(--success-line)" };
const FOCUS = { fill: "var(--accent)", ring: "var(--accent-line)" };
const CHANGED = { fill: "var(--medium)", ring: "var(--medium-line)" };

function colourFor(node: GraphNode, isFocus: boolean) {
  if (isFocus) return FOCUS;
  if (node.finding_count > 0 && node.max_severity) return SEVERITY_FILL[node.max_severity] ?? CLEAN;
  if (node.changed) return CHANGED;
  return CLEAN;
}

/** Single letter inside the circle, so node kind reads without hovering. */
function glyphFor(node: GraphNode): string {
  const initial = String(node.type || "?").charAt(0).toUpperCase();
  return node.finding_count > 0 ? "!" : initial;
}

export function KnowledgeGraphCanvas({
  nodes,
  edges,
  selectedId,
  onSelect,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedId: string | null;
  onSelect: (nodeId: string) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragState = useRef<{ x: number; y: number; panX: number; panY: number } | null>(null);

  // A repository graph can reach 1200 nodes. Laying that out is O(n²) per
  // iteration — several seconds — and the result is an unreadable hairball, so
  // render the structurally important core instead. Centrality is exactly the
  // ranking for that, and the selection plus its neighbours are always kept so
  // clicking through never loses context.
  const { visibleNodes, visibleEdges } = useMemo(() => {
    if (nodes.length <= MAX_RENDERED) {
      return { visibleNodes: nodes, visibleEdges: edges };
    }

    const keep = new Set<string>();
    if (selectedId) {
      keep.add(selectedId);
      for (const edge of edges) {
        if (edge.source === selectedId) keep.add(edge.target);
        if (edge.target === selectedId) keep.add(edge.source);
      }
    }

    const ranked = [...nodes].sort(
      (a, b) => Number(b.metrics?.centrality ?? 0) - Number(a.metrics?.centrality ?? 0),
    );
    for (const node of ranked) {
      if (keep.size >= MAX_RENDERED) break;
      keep.add(node.id);
    }

    return {
      visibleNodes: nodes.filter((n) => keep.has(n.id)),
      visibleEdges: edges.filter((e) => keep.has(e.source) && keep.has(e.target)),
    };
  }, [nodes, edges, selectedId]);

  // Laying out is O(n²) per iteration, so it must not rerun on hover or pan.
  const layout = useMemo(
    () =>
      layoutGraph(visibleNodes, visibleEdges, {
        width: WIDTH,
        height: HEIGHT,
        focusId: selectedId,
      }),
    [visibleNodes, visibleEdges, selectedId],
  );

  const truncated = visibleNodes.length < nodes.length;

  const nodeById = useMemo(
    () => new Map(layout.nodes.map((n) => [n.node.id, n])),
    [layout],
  );

  const selected = selectedId ? nodeById.get(selectedId) : undefined;

  // Edges touching the selection are drawn in the accent colour and on top.
  const isConnected = (edge: GraphEdge) =>
    selectedId != null && (edge.source === selectedId || edge.target === selectedId);

  const onPointerDown = (event: React.PointerEvent) => {
    dragState.current = { x: event.clientX, y: event.clientY, panX: pan.x, panY: pan.y };
    (event.target as Element).setPointerCapture?.(event.pointerId);
  };
  const onPointerMove = (event: React.PointerEvent) => {
    const state = dragState.current;
    if (!state) return;
    setPan({
      x: state.panX + (event.clientX - state.x),
      y: state.panY + (event.clientY - state.y),
    });
  };
  const onPointerUp = () => {
    dragState.current = null;
  };

  const cypher = truncated
    ? `MATCH (n)-[r]-(m) RETURN n, r, m ORDER BY n.centrality DESC LIMIT ${visibleNodes.length}`
    : `MATCH (n)-[r]-(m) RETURN n, r, m LIMIT ${visibleNodes.length}`;

  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* Query caption — states what the canvas is showing. */}
      <div className="pointer-events-none absolute left-1/2 top-3 z-10 max-w-[80%] -translate-x-1/2 truncate rounded-md border border-line bg-canvas/90 px-3 py-1.5 font-mono text-[11px] text-ink-muted backdrop-blur">
        {cypher}
      </div>

      {/* Zoom controls */}
      <div className="absolute right-3 top-3 z-10 flex flex-col gap-1">
        {[
          { label: "+", action: () => setZoom((z) => Math.min(2.5, z * 1.25)), title: "Zoom in" },
          { label: "−", action: () => setZoom((z) => Math.max(0.4, z / 1.25)), title: "Zoom out" },
          {
            label: "⌂",
            action: () => {
              setZoom(1);
              setPan({ x: 0, y: 0 });
            },
            title: "Reset view",
          },
        ].map((control) => (
          <button
            key={control.title}
            type="button"
            onClick={control.action}
            title={control.title}
            className="flex h-8 w-8 items-center justify-center rounded-md border border-line bg-canvas text-ink-muted shadow-sm transition-colors hover:bg-surface hover:text-ink"
          >
            {control.label}
          </button>
        ))}
      </div>

      <svg
        viewBox={`${layout.viewBox.x} ${layout.viewBox.y} ${layout.viewBox.width} ${layout.viewBox.height}`}
        className="h-full w-full cursor-grab active:cursor-grabbing"
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
      >
        <g transform={`translate(${pan.x} ${pan.y}) scale(${zoom})`}>
          {/* Edges first so nodes sit on top of them. */}
          {layout.edges.map(({ edge, source, target }) => {
            const connected = isConnected(edge);
            const midX = (source.x + target.x) / 2;
            const midY = (source.y + target.y) / 2;
            return (
              <g key={edge.id}>
                <line
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke={connected ? "var(--accent)" : "var(--line)"}
                  strokeWidth={connected ? 2 : 1}
                  strokeOpacity={selectedId && !connected ? 0.35 : 1}
                />
                {connected && (
                  <text
                    x={midX}
                    y={midY - 4}
                    textAnchor="middle"
                    className="pointer-events-none select-none font-mono uppercase"
                    style={{
                      fontSize: 9,
                      fill: "var(--ink-subtle)",
                      paintOrder: "stroke",
                      stroke: "var(--canvas)",
                      strokeWidth: 4,
                    }}
                  >
                    {edge.type}
                  </text>
                )}
              </g>
            );
          })}

          {/* Nodes */}
          {layout.nodes.map((laid) => {
            const isFocus = laid.node.id === selectedId;
            const colour = colourFor(laid.node, isFocus);
            const dimmed = selectedId != null && !isFocus &&
              !layout.edges.some(
                ({ edge }) =>
                  (edge.source === selectedId && edge.target === laid.node.id) ||
                  (edge.target === selectedId && edge.source === laid.node.id),
              );
            return (
              <g
                key={laid.node.id}
                transform={`translate(${laid.x} ${laid.y})`}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(laid.node.id);
                }}
                className="cursor-pointer"
                opacity={dimmed ? 0.4 : 1}
              >
                {isFocus && (
                  <circle r={laid.radius + 7} fill="var(--accent)" opacity={0.16} />
                )}
                <circle
                  r={laid.radius}
                  fill={colour.fill}
                  stroke={colour.ring}
                  strokeWidth={isFocus ? 3 : 2}
                />
                <text
                  textAnchor="middle"
                  dy={4}
                  className="pointer-events-none select-none font-semibold"
                  style={{ fontSize: 11, fill: "#fff" }}
                >
                  {glyphFor(laid.node)}
                </text>
                <text
                  textAnchor="middle"
                  y={laid.radius + 13}
                  className="pointer-events-none select-none font-mono"
                  style={{
                    fontSize: 10,
                    fill: "var(--ink-muted)",
                    paintOrder: "stroke",
                    stroke: "var(--canvas)",
                    strokeWidth: 3,
                  }}
                >
                  {laid.node.label.length > 22
                    ? `${laid.node.label.slice(0, 21)}…`
                    : laid.node.label}
                </text>
              </g>
            );
          })}
        </g>
      </svg>

      {selected && <PropertiesPanel laid={selected} nodeById={nodeById} onSelect={onSelect} />}
      <Legend truncated={truncated} shown={visibleNodes.length} totalNodes={nodes.length} />
    </div>
  );
}

function PropertiesPanel({
  laid,
  nodeById,
  onSelect,
}: {
  laid: LaidOutNode;
  nodeById: Map<string, LaidOutNode>;
  onSelect: (id: string) => void;
}) {
  const node = laid.node;
  const centrality = Number(node.metrics?.centrality ?? 0);
  // KNN neighbours computed server-side during analysis.
  const similar = Array.isArray(node.metrics?.similar)
    ? (node.metrics.similar as { id: string; score: number }[])
    : [];

  const rows: [string, string][] = [
    ["type", String(node.type)],
    ["findings", String(node.finding_count)],
    ["severity", node.max_severity ?? "—"],
    ["centrality", centrality ? centrality.toFixed(3) : "—"],
    ["changed", node.changed ? "yes" : "no"],
    ["language", node.language ?? "—"],
  ];

  return (
    <div className="absolute right-3 top-1/2 z-20 w-60 -translate-y-1/2 rounded-lg border border-line bg-overlay p-4 shadow-[var(--shadow-md)]">
      <p className="truncate text-[13px] font-semibold text-ink">{node.label}</p>
      {node.file_path && (
        <p className="mt-0.5 truncate font-mono text-[10px] text-ink-subtle">{node.file_path}</p>
      )}

      <dl className="mt-3 space-y-1.5">
        {rows.map(([key, value]) => (
          <div key={key} className="flex items-baseline justify-between gap-3">
            <dt className="font-mono text-[10px] text-ink-subtle">{key}</dt>
            <dd className="truncate font-mono text-[11px] font-medium text-ink">{value}</dd>
          </div>
        ))}
      </dl>

      {similar.length > 0 && (
        <div className="mt-3 border-t border-line pt-3">
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-subtle">
            Nearest neighbours
          </p>
          <ul className="mt-1.5 space-y-1">
            {similar.map((entry) => {
              const target = nodeById.get(entry.id);
              return (
                <li key={entry.id}>
                  <button
                    type="button"
                    onClick={() => target && onSelect(entry.id)}
                    disabled={!target}
                    className={cn(
                      "flex w-full items-baseline justify-between gap-2 text-left text-[11px]",
                      target ? "text-accent hover:underline" : "text-ink-subtle",
                    )}
                  >
                    <span className="truncate">{target?.node.label ?? entry.id}</span>
                    <span className="font-mono text-[10px] text-ink-subtle">
                      {entry.score.toFixed(2)}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function Legend({
  truncated,
  shown,
  totalNodes,
}: {
  truncated: boolean;
  shown: number;
  totalNodes: number;
}) {
  return (
    <div className="absolute bottom-3 left-3 z-10 rounded-lg border border-line bg-overlay/95 p-3 shadow-sm backdrop-blur">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-subtle">Legend</p>
      <ul className="mt-2 space-y-1.5">
        {[
          { colour: "var(--accent)", label: "Selected" },
          { colour: "var(--critical)", label: "Critical findings" },
          { colour: "var(--high)", label: "High findings" },
          { colour: "var(--medium)", label: "Changed / medium" },
          { colour: "var(--success)", label: "Clean" },
        ].map((entry) => (
          <li key={entry.label} className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: entry.colour }}
            />
            <span className="text-[11px] text-ink-muted">{entry.label}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 border-t border-line pt-2 text-[10px] leading-relaxed text-ink-subtle">
        Size follows centrality. Drag to pan, click a node for properties.
        {truncated && (
          <>
            <br />
            Showing the {shown} most central of {totalNodes} nodes.
          </>
        )}
      </p>
    </div>
  );
}
