"use client";

import { useMemo, useRef, useState } from "react";
import { hubLayout, layoutGraph, MAX_LABEL_CHARS, type LaidOutNode } from "./forceLayout";
import type { GraphEdge, GraphNode, Severity } from "@/types/api";
import { cn } from "@/lib/utils";

const WIDTH = 1000;
const HEIGHT = 620;

/** Beyond this the layout is slow and the picture is an unreadable hairball. */
const MAX_RENDERED = 70;

/** Past this, a relationship type on every edge is noise rather than labelling. */
const MAX_LABELLED_EDGES = 44;

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

/** Neo4j-style node label: `file` → `:File`, capped so it stays inside the circle. */
function typeCaption(node: GraphNode): string {
  const raw = String(node.type || "node").replace(/_/g, " ");
  const name = raw.charAt(0).toUpperCase() + raw.slice(1);
  return `:${name.length > 10 ? `${name.slice(0, 9)}…` : name}`;
}

/** Second caption line, inside the circle — the node's own name, Neo4j style.
 *
 * How much fits is a function of the circle, not a fixed count: a 10px
 * semibold glyph is ~5.6px wide, and text has to clear the curve at the
 * baseline rather than at the diameter. */
function shortName(node: GraphNode, radius: number): string {
  const base = node.label.split(/[\\/]/).pop() ?? node.label;
  const stem = base.replace(/\.[a-z0-9]+$/i, "") || base;
  const fits = Math.max(4, Math.floor((Math.sqrt(Math.max(1, radius * radius - 81)) * 2) / 5.6));
  return stem.length > fits ? `${stem.slice(0, fits - 1)}…` : stem;
}

function truncateLabel(label: string): string {
  return label.length > MAX_LABEL_CHARS ? `${label.slice(0, MAX_LABEL_CHARS - 1)}…` : label;
}

/** The line under the focus node — the equivalent of the reference's "100% fraud". */
function focusCaption(node: GraphNode): string {
  if (node.finding_count === 0) return "no findings";
  const noun = node.finding_count === 1 ? "finding" : "findings";
  return node.max_severity
    ? `${node.finding_count} ${node.max_severity} ${noun}`
    : `${node.finding_count} ${noun}`;
}

/** Cypher caption, coloured the way the Neo4j browser colours a query. */
function CypherBar({
  focus,
  relationship,
  limit,
  ordered,
}: {
  focus: GraphNode | null;
  relationship: string;
  limit: number;
  ordered: boolean;
}) {
  const kw = "text-[#8250df] dark:text-[#d2a8ff]";
  const nd = "text-[#1a7f37] dark:text-[#3fb950]";
  const rel = "text-[#9a6700] dark:text-[#d29922]";
  const prop = "text-accent";
  const num = "text-[#bc4c00] dark:text-[#f0883e]";

  return (
    <div className="pointer-events-none absolute left-1/2 top-3 z-10 max-w-[86%] -translate-x-1/2 truncate rounded-md border border-line bg-canvas/90 px-3 py-1.5 font-mono text-[11px] text-ink-muted shadow-sm backdrop-blur">
      <span className={kw}>MATCH</span> (t
      {focus && <span className={nd}>{typeCaption(focus)}</span>}
      {focus && (
        <>
          {" {name: "}
          <span className={prop}>&apos;{truncateLabel(focus.label)}&apos;</span>
          {"}"}
        </>
      )}
      )-[r<span className={rel}>:{relationship}</span>
      <span className={num}>*1..2</span>]-(n) <span className={kw}>RETURN</span> t,r,n{" "}
      {ordered && (
        <>
          <span className={kw}>ORDER BY</span> n.centrality <span className={kw}>DESC</span>{" "}
        </>
      )}
      <span className={kw}>LIMIT</span> <span className={num}>{limit}</span>
    </div>
  );
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
  //
  // With a node selected the question on screen is "what does this touch", so
  // the hub layout answers it directly: focus at the centre, one ring per hop.
  // With nothing selected there is no hub to organise around, and the settled
  // force layout showing overall shape is the right picture.
  const layout = useMemo(
    () =>
      selectedId
        ? hubLayout(visibleNodes, visibleEdges, {
            width: WIDTH,
            height: HEIGHT,
            focusId: selectedId,
          })
        : layoutGraph(visibleNodes, visibleEdges, { width: WIDTH, height: HEIGHT }),
    [visibleNodes, visibleEdges, selectedId],
  );

  const truncated = visibleNodes.length < nodes.length;

  const nodeById = useMemo(
    () => new Map(layout.nodes.map((n) => [n.node.id, n])),
    [layout],
  );

  const selected = selectedId ? nodeById.get(selectedId) : undefined;

  // Neighbours of the selection, resolved once: the per-node version of this
  // scanned every edge for every node, which is quadratic on a dense graph.
  const neighbourIds = useMemo(() => {
    const ids = new Set<string>();
    if (!selectedId) return ids;
    for (const edge of visibleEdges) {
      if (edge.source === selectedId) ids.add(edge.target);
      if (edge.target === selectedId) ids.add(edge.source);
    }
    return ids;
  }, [visibleEdges, selectedId]);

  // Edges touching the selection are drawn in the accent colour and on top.
  const isConnected = (edge: GraphEdge) =>
    selectedId != null && (edge.source === selectedId || edge.target === selectedId);

  // The relationship named in the Cypher caption is whichever type actually
  // dominates the edges on screen, so the caption describes this graph.
  const dominantRelationship = useMemo(() => {
    const counts = new Map<string, number>();
    for (const edge of visibleEdges) {
      counts.set(edge.type, (counts.get(edge.type) ?? 0) + 1);
    }
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
    return (top ?? "DEPENDS_ON").toUpperCase().replace(/[^A-Z0-9]+/g, "_");
  }, [visibleEdges]);

  const labelEdges = visibleEdges.length <= MAX_LABELLED_EDGES;

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

  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* Query caption — states what the canvas is showing. */}
      <CypherBar
        focus={selected?.node ?? null}
        relationship={dominantRelationship}
        limit={visibleNodes.length}
        ordered={truncated}
      />

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
            // Relationship labels ride along their edge, as in the Neo4j
            // browser; a horizontal label on a near-vertical spoke reads as
            // belonging to whatever it happens to overlap.
            // Rounded for the same reason the layout rounds its coordinates:
            // `Math.atan2` is not bit-identical across engines, and an unrounded
            // transform string trips React's hydration comparison.
            let angle =
              Math.round((Math.atan2(target.y - source.y, target.x - source.x) * 18000) / Math.PI) /
              100;
            if (angle > 90) angle -= 180;
            if (angle < -90) angle += 180;
            return (
              <g key={edge.id}>
                <line
                  x1={source.x}
                  y1={source.y}
                  x2={target.x}
                  y2={target.y}
                  stroke={connected ? "var(--accent)" : "var(--line)"}
                  strokeWidth={connected ? 1.8 : 1}
                  strokeOpacity={selectedId && !connected ? 0.4 : 1}
                />
                {(connected || labelEdges) && (
                  <text
                    x={midX}
                    y={midY}
                    transform={`rotate(${angle} ${midX} ${midY})`}
                    textAnchor="middle"
                    dy={-4}
                    className="pointer-events-none select-none font-mono uppercase"
                    style={{
                      fontSize: 9,
                      letterSpacing: "0.04em",
                      fill: "var(--ink-subtle)",
                      opacity: connected ? 1 : 0.75,
                      paintOrder: "stroke",
                      stroke: "var(--canvas)",
                      strokeWidth: 4,
                    }}
                  >
                    {edge.type.toUpperCase().replace(/[^A-Z0-9]+/g, "_")}
                  </text>
                )}
              </g>
            );
          })}

          {/* Nodes */}
          {layout.nodes.map((laid) => {
            const isFocus = laid.node.id === selectedId;
            const colour = colourFor(laid.node, isFocus);
            const dimmed = selectedId != null && !isFocus && !neighbourIds.has(laid.node.id);
            return (
              <g
                key={laid.node.id}
                transform={`translate(${laid.x} ${laid.y})`}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(laid.node.id);
                }}
                className="cursor-pointer"
                opacity={dimmed ? 0.45 : 1}
              >
                {/* Focus halo: two rings, so the hub is unmistakable even when
                    a neighbour happens to be larger. */}
                {isFocus && (
                  <>
                    <circle r={laid.radius + 12} fill={colour.fill} opacity={0.1} />
                    <circle
                      r={laid.radius + 6}
                      fill="none"
                      stroke={colour.fill}
                      strokeWidth={1.5}
                      strokeOpacity={0.45}
                      strokeDasharray="3 4"
                    />
                  </>
                )}
                <circle
                  r={laid.radius}
                  fill={colour.fill}
                  stroke={colour.ring}
                  strokeWidth={isFocus ? 3 : 2}
                />
                {/* Two captions inside the circle: `:Type` over the name, the
                    way a Neo4j node renders its label and its key property. */}
                <text
                  textAnchor="middle"
                  dy={-3}
                  className="pointer-events-none select-none font-mono"
                  style={{ fontSize: 7.5, fill: "#fff", fillOpacity: 0.82 }}
                >
                  {typeCaption(laid.node)}
                </text>
                <text
                  textAnchor="middle"
                  dy={9}
                  className="pointer-events-none select-none font-semibold"
                  style={{ fontSize: 10, fill: "#fff" }}
                >
                  {shortName(laid.node, laid.radius)}
                </text>

                {/* The full name only when the circle had to abbreviate it. */}
                {shortName(laid.node, laid.radius) !== laid.node.label && (
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
                    {truncateLabel(laid.node.label)}
                  </text>
                )}

                {isFocus && (
                  <text
                    textAnchor="middle"
                    y={laid.radius + 26}
                    className="pointer-events-none select-none font-mono font-semibold"
                    style={{
                      fontSize: 9.5,
                      fill: colour.fill,
                      paintOrder: "stroke",
                      stroke: "var(--canvas)",
                      strokeWidth: 3,
                    }}
                  >
                    {focusCaption(laid.node)}
                  </text>
                )}
              </g>
            );
          })}
        </g>
      </svg>

      {selected && <PropertiesPanel laid={selected} nodeById={nodeById} onSelect={onSelect} />}
      <Legend
        truncated={truncated}
        shown={visibleNodes.length}
        totalNodes={nodes.length}
        hasSelection={Boolean(selected)}
      />
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
  hasSelection,
}: {
  truncated: boolean;
  shown: number;
  totalNodes: number;
  hasSelection: boolean;
}) {
  return (
    <div className="absolute bottom-3 left-3 z-10 rounded-lg border border-line bg-overlay/95 p-3 shadow-sm backdrop-blur">
      <p className="font-mono text-[10px] uppercase tracking-wider text-ink-subtle">Legend</p>
      <ul className="mt-2 space-y-1.5">
        {[
          // `--low` is the same blue as `--accent`, so the selected node is
          // marked by its ring rather than its fill — the legend has to show
          // that, or the two blues read as the same thing.
          { colour: "var(--accent)", label: "Selected", ring: true },
          { colour: "var(--critical)", label: "Critical findings" },
          { colour: "var(--high)", label: "High findings" },
          { colour: "var(--medium)", label: "Changed / medium" },
          { colour: "var(--low)", label: "Low findings" },
          { colour: "var(--success)", label: "Clean" },
        ].map((entry) => (
          <li key={entry.label} className="flex items-center gap-2">
            <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center">
              <span
                className={cn(
                  "inline-block h-2.5 w-2.5 rounded-full",
                  entry.ring && "ring-2 ring-accent/45 ring-offset-2 ring-offset-overlay",
                )}
                style={{ background: entry.colour }}
              />
            </span>
            <span className="text-[11px] text-ink-muted">{entry.label}</span>
          </li>
        ))}
      </ul>
      {/* Edge colouring and the rings only mean anything once something is
          selected — with nothing selected the canvas is a plain overview. */}
      {hasSelection && (
        <div className="mt-2 space-y-1.5 border-t border-line pt-2">
          <div className="flex items-center gap-2">
            <span className="inline-block h-0.5 w-6 rounded-full bg-accent" />
            <span className="font-mono text-[10px] text-ink-muted">1 hop from selection</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-px w-6 rounded-full bg-line" />
            <span className="font-mono text-[10px] text-ink-muted">further out</span>
          </div>
        </div>
      )}

      <p className="mt-2 border-t border-line pt-2 text-[10px] leading-relaxed text-ink-subtle">
        {hasSelection
          ? "Each ring is one hop from the selected node. "
          : "Click a node to centre the graph on it. "}
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
