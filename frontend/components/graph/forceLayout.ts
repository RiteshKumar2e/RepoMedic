import type { GraphEdge, GraphNode } from "@/types/api";

/**
 * Force-directed layout, run to completion before render.
 *
 * A dependency-free implementation of the standard three forces: Coulomb
 * repulsion between every pair, Hooke springs along edges, and a weak pull
 * toward the centre so disconnected components do not drift away.
 *
 * It settles synchronously rather than animating, because a knowledge graph is
 * something you read rather than watch — and a stable layout means the same
 * repository always looks the same, so positions are memorable between visits.
 * Initial placement uses the golden angle rather than random jitter for that
 * same reason.
 */

export interface LaidOutNode {
  node: GraphNode;
  x: number;
  y: number;
  radius: number;
}

export interface LaidOutEdge {
  edge: GraphEdge;
  source: LaidOutNode;
  target: LaidOutNode;
}

export interface Layout {
  nodes: LaidOutNode[];
  edges: LaidOutEdge[];
  width: number;
  height: number;
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

/** Gap left between circles so the label underneath each stays legible. */
const LABEL_PADDING = 16;

/** Node radius scales with centrality — important modules read as bigger. */
function radiusFor(node: GraphNode, isFocus: boolean): number {
  const centrality = Number(node.metrics?.centrality ?? 0);
  const base = 13 + centrality * 11;
  return isFocus ? base + 7 : base;
}

/** Separate any pair of circles closer than their radii plus label room. */
function resolveCollisions(placed: LaidOutNode[]): void {
  for (let i = 0; i < placed.length; i++) {
    for (let j = i + 1; j < placed.length; j++) {
      const a = placed[i];
      const b = placed[j];
      const minimum = a.radius + b.radius + LABEL_PADDING;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.hypot(dx, dy);
      if (distance >= minimum || distance === 0) continue;
      const push = (minimum - distance) / 2;
      const nx = dx / distance;
      const ny = dy / distance;
      a.x -= nx * push;
      a.y -= ny * push;
      b.x += nx * push;
      b.y += ny * push;
    }
  }
}

export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: { width: number; height: number; focusId?: string | null; iterations?: number },
): Layout {
  const { width, height, focusId = null, iterations = 320 } = options;
  const centreX = width / 2;
  const centreY = height / 2;

  const placed: LaidOutNode[] = nodes.map((node, index) => {
    // Golden-angle spiral: even initial spread, and deterministic.
    const angle = index * GOLDEN_ANGLE;
    const spread = Math.sqrt(index / Math.max(1, nodes.length)) * Math.min(width, height) * 0.38;
    return {
      node,
      x: centreX + Math.cos(angle) * spread,
      y: centreY + Math.sin(angle) * spread,
      radius: radiusFor(node, node.id === focusId),
    };
  });

  const byId = new Map(placed.map((p) => [p.node.id, p]));
  const links = edges
    .map((edge) => ({
      edge,
      source: byId.get(edge.source),
      target: byId.get(edge.target),
    }))
    .filter((l): l is LaidOutEdge => Boolean(l.source && l.target));

  // The focus node is pinned at the centre so the view always has an anchor.
  const focus = focusId ? byId.get(focusId) : undefined;

  const area = width * height;
  const ideal = Math.sqrt(area / Math.max(1, placed.length)) * 0.62;
  const velocities = placed.map(() => ({ vx: 0, vy: 0 }));

  for (let step = 0; step < iterations; step++) {
    // Cooling schedule: large corrections early, fine adjustment later.
    const alpha = 1 - step / iterations;
    const damping = 0.82;

    // ---- repulsion (every pair) --------------------------------------
    for (let i = 0; i < placed.length; i++) {
      for (let j = i + 1; j < placed.length; j++) {
        const a = placed[i];
        const b = placed[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let distance = Math.hypot(dx, dy);
        if (distance < 0.01) {
          // Coincident nodes would produce NaN; nudge them apart deterministically.
          dx = (i % 2 === 0 ? 1 : -1) * 0.5;
          dy = (j % 2 === 0 ? 1 : -1) * 0.5;
          distance = 0.7;
        }
        const force = ((ideal * ideal) / distance) * 0.045 * alpha;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        velocities[i].vx += fx;
        velocities[i].vy += fy;
        velocities[j].vx -= fx;
        velocities[j].vy -= fy;
      }
    }

    // ---- springs (edges) ---------------------------------------------
    for (const link of links) {
      const a = link.source;
      const b = link.target;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.max(0.01, Math.hypot(dx, dy));
      const force = ((distance - ideal) / distance) * 0.09 * alpha;
      const fx = dx * force;
      const fy = dy * force;
      const ai = placed.indexOf(a);
      const bi = placed.indexOf(b);
      velocities[ai].vx += fx;
      velocities[ai].vy += fy;
      velocities[bi].vx -= fx;
      velocities[bi].vy -= fy;
    }

    // ---- centring + integrate ----------------------------------------
    for (let i = 0; i < placed.length; i++) {
      const p = placed[i];
      velocities[i].vx += (centreX - p.x) * 0.006 * alpha;
      velocities[i].vy += (centreY - p.y) * 0.006 * alpha;

      velocities[i].vx *= damping;
      velocities[i].vy *= damping;

      p.x += velocities[i].vx;
      p.y += velocities[i].vy;
    }

    // Repulsion alone is radius-blind, so large nodes still overlap.
    resolveCollisions(placed);

    if (focus) {
      focus.x = centreX;
      focus.y = centreY;
    }
  }

  // Fit to the viewport by scaling, not clamping. Clamping pins every outlying
  // node onto the same boundary coordinate, which stacks them into an
  // unreadable pile exactly where the graph is most crowded.
  const margin = 46;
  const xs = placed.map((p) => p.x);
  const ys = placed.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);

  const spanX = maxX - minX;
  const spanY = maxY - minY;
  const usableWidth = width - margin * 2;
  const usableHeight = height - margin * 2;

  // Only shrink; blowing a small graph up to fill the canvas looks wrong.
  const scale = Math.min(
    1,
    spanX > 0 ? usableWidth / spanX : 1,
    spanY > 0 ? usableHeight / spanY : 1,
  );

  const offsetX = centreX - ((minX + maxX) / 2) * scale;
  const offsetY = centreY - ((minY + maxY) / 2) * scale;

  for (const p of placed) {
    p.x = p.x * scale + offsetX;
    p.y = p.y * scale + offsetY;
    // Radii deliberately survive scaling: their size encodes centrality, and
    // shrinking them to fit would erase the signal the layout exists to show.
  }

  // Scaling positions while holding radii fixed can reintroduce overlap, so
  // settle collisions again at the final size.
  for (let pass = 0; pass < 12; pass++) {
    resolveCollisions(placed);
  }

  // Re-pin the focus last; the fit above moves it off centre.
  if (focus) {
    const dx = centreX - focus.x;
    const dy = centreY - focus.y;
    for (const p of placed) {
      p.x += dx;
      p.y += dy;
    }
  }

  return { nodes: placed, edges: links, width, height };
}
