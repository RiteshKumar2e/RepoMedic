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
  /** Actual extent of the laid-out content, for the SVG viewBox.
   *
   * Spacing labels apart can push nodes past the nominal canvas, and a fixed
   * viewBox would simply clip them. Reporting the real bounds lets the SVG
   * scale to whatever the layout needed instead. */
  viewBox: { x: number; y: number; width: number; height: number };
}

const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));

/** Vertical breathing room between a circle and the one below it. */
const LABEL_PADDING = 16;

/* Labels sit under each circle and are far wider than they are tall, so
   collision has to be elliptical. Treating nodes as circles separates them just
   enough for the dots and leaves the text overlapping into a smear. */
const LABEL_CHAR_WIDTH = 5.4; // ≈ 10px monospace
export const MAX_LABEL_CHARS = 18; // matches the truncation in the renderer

/** Node radius scales with centrality — important modules read as bigger.
 *
 * The floor is set by the text that sits *inside* the circle: a `:Type` caption
 * of nine characters at 7px needs roughly 19px of half-width to clear the edge. */
function radiusFor(node: GraphNode, isFocus: boolean): number {
  const centrality = Number(node.metrics?.centrality ?? 0);
  const base = 21 + centrality * 9;
  return isFocus ? base + 7 : base;
}

/** Half-width of a node's rendered label, floored at the circle itself. */
function labelHalfWidth(node: LaidOutNode): number {
  const chars = Math.min(node.node.label.length, MAX_LABEL_CHARS);
  return Math.max(node.radius, (chars * LABEL_CHAR_WIDTH) / 2);
}

/**
 * Separate overlapping nodes, treating each as an ellipse wide enough for its
 * label. Correction is applied along the axis with the smaller overlap, so
 * nodes slide sideways when text collides but stay vertically compact.
 */
function resolveCollisions(placed: LaidOutNode[]): void {
  for (let i = 0; i < placed.length; i++) {
    for (let j = i + 1; j < placed.length; j++) {
      const a = placed[i];
      const b = placed[j];

      const minX = labelHalfWidth(a) + labelHalfWidth(b) + 8;
      const minY = a.radius + b.radius + LABEL_PADDING;

      const gapX = Math.abs(b.x - a.x);
      const gapY = Math.abs(b.y - a.y);

      // Boxes clear of each other on either axis cannot overlap.
      if (gapX >= minX || gapY >= minY) continue;

      const overlapX = minX - gapX;
      const overlapY = minY - gapY;

      if (overlapX < overlapY) {
        const push = overlapX / 2;
        const dir = b.x >= a.x ? 1 : -1;
        a.x -= dir * push;
        b.x += dir * push;
      } else {
        const push = overlapY / 2;
        const dir = b.y >= a.y ? 1 : -1;
        a.y -= dir * push;
        b.y += dir * push;
      }
    }
  }
}

/** Radial fallback kept for the pre-scale passes, where only dots matter. */
function resolveCircleCollisions(placed: LaidOutNode[]): void {
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

/**
 * Round coordinates before they leave the layout.
 *
 * `Math.sin`, `Math.cos` and friends are implementation-defined in JS, so the
 * V8 that renders on the server and the V8 in the browser can disagree in the
 * last couple of bits. That is invisible on screen but not to React, which
 * compares the two `viewBox` strings during hydration and reports a mismatch.
 * Two decimals is far finer than a pixel and identical on both sides.
 */
function quantise(value: number): number {
  return Math.round(value * 100) / 100;
}

function quantiseLayout(placed: LaidOutNode[]): void {
  for (const p of placed) {
    p.x = quantise(p.x);
    p.y = quantise(p.y);
    p.radius = quantise(p.radius);
  }
}

/** Bounding box covering every circle and its label, never smaller than the canvas. */
function contentBounds(
  placed: LaidOutNode[],
  width: number,
  height: number,
): { x: number; y: number; width: number; height: number } {
  if (placed.length === 0) return { x: 0, y: 0, width, height };

  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  for (const p of placed) {
    const halfWidth = labelHalfWidth(p);
    minX = Math.min(minX, p.x - halfWidth);
    maxX = Math.max(maxX, p.x + halfWidth);
    minY = Math.min(minY, p.y - p.radius);
    // Labels hang below the circle.
    maxY = Math.max(maxY, p.y + p.radius + 18);
  }

  const pad = 24;
  minX -= pad;
  maxX += pad;
  // The query caption floats over the top of the canvas, so reserve enough
  // headroom that it does not land on top of the outermost node.
  minY -= pad + 34;
  maxY += pad;

  // Never zoom in past the nominal canvas: a three-node graph blown up to full
  // bleed looks broken.
  const boxWidth = Math.max(width, maxX - minX);
  const boxHeight = Math.max(height, maxY - minY);
  const centreX = (minX + maxX) / 2;
  const centreY = (minY + maxY) / 2;

  return {
    x: quantise(centreX - boxWidth / 2),
    y: quantise(centreY - boxHeight / 2),
    width: quantise(boxWidth),
    height: quantise(boxHeight),
  };
}

/** Minimum clearance between one ring of nodes and the next one out. */
const RING_GAP = 116;

/** Builds the undirected adjacency used by the hop-based layout. */
function adjacencyOf(links: LaidOutEdge[], ids: string[]): Map<string, Set<string>> {
  const adjacency = new Map<string, Set<string>>();
  for (const id of ids) adjacency.set(id, new Set());
  for (const link of links) {
    adjacency.get(link.source.node.id)?.add(link.target.node.id);
    adjacency.get(link.target.node.id)?.add(link.source.node.id);
  }
  return adjacency;
}

/**
 * Hub-and-spoke layout: the focus node sits at the centre and everything else
 * is placed on a ring per hop distance, the way a Neo4j browser renders a
 * `(t)-[r*1..2]-(n)` expansion.
 *
 * A settled force layout answers "what does this repository look like"; this
 * answers "what does *this* node touch", which is the question the canvas is
 * actually being used for once a node is selected. Reading a hop count off a
 * ring is immediate, whereas in a spring layout it has to be traced by eye.
 *
 * Ring radius comes from how much arc the nodes on it need, so a hub with
 * thirty neighbours pushes its ring out rather than overlapping labels. Angles
 * are inherited from a node's parents on the inner ring, which keeps each
 * subtree in its own wedge and stops edges crossing the hub.
 */
export function hubLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  options: { width: number; height: number; focusId: string },
): Layout {
  const { width, height, focusId } = options;
  const centreX = width / 2;
  const centreY = height / 2;

  const placed: LaidOutNode[] = nodes.map((node) => ({
    node,
    x: centreX,
    y: centreY,
    radius: radiusFor(node, node.id === focusId),
  }));
  const byId = new Map(placed.map((p) => [p.node.id, p]));

  const links = edges
    .map((edge) => ({
      edge,
      source: byId.get(edge.source),
      target: byId.get(edge.target),
    }))
    .filter((l): l is LaidOutEdge => Boolean(l.source && l.target));

  const adjacency = adjacencyOf(links, nodes.map((n) => n.id));

  // ---- hop distance from the focus ------------------------------------
  const hops = new Map<string, number>();
  hops.set(focusId, 0);
  let frontier = [focusId];
  let depth = 0;
  while (frontier.length > 0) {
    depth += 1;
    const next: string[] = [];
    for (const id of frontier) {
      for (const neighbour of adjacency.get(id) ?? []) {
        if (hops.has(neighbour)) continue;
        hops.set(neighbour, depth);
        next.push(neighbour);
      }
    }
    frontier = next;
  }

  // Nodes with no path to the focus still have to go somewhere; one ring
  // beyond the connected component reads correctly as "not reachable from
  // here" without hiding them.
  const reachableDepth = Math.max(0, ...hops.values());
  const orphanRing = reachableDepth + 1;
  for (const p of placed) {
    if (!hops.has(p.node.id)) hops.set(p.node.id, orphanRing);
  }

  const rings = new Map<number, LaidOutNode[]>();
  for (const p of placed) {
    const hop = hops.get(p.node.id) ?? orphanRing;
    if (hop === 0) continue;
    const ring = rings.get(hop);
    if (ring) ring.push(p);
    else rings.set(hop, [p]);
  }

  const focus = byId.get(focusId);
  const angles = new Map<string, number>([[focusId, 0]]);
  let innerRadius = (focus?.radius ?? 24) + 30;

  const ringNumbers = [...rings.keys()].sort((a, b) => a - b);
  for (const hop of ringNumbers) {
    const ring = rings.get(hop) ?? [];

    // Preferred angle: the circular mean of whichever parents are already
    // placed, so a node lands in the same direction as what it hangs off.
    const preferred = ring.map((p, index) => {
      let sinSum = 0;
      let cosSum = 0;
      let parents = 0;
      for (const neighbour of adjacency.get(p.node.id) ?? []) {
        const parentAngle = angles.get(neighbour);
        const parentHop = hops.get(neighbour) ?? 0;
        // The hub is at the centre, so it has no direction to inherit — the
        // first ring would otherwise collapse onto a single bearing.
        if (parentAngle === undefined || parentHop === 0 || parentHop >= hop) continue;
        sinSum += Math.sin(parentAngle);
        cosSum += Math.cos(parentAngle);
        parents += 1;
      }
      // No placed parent (the first ring, or orphans) — fall back to an even
      // deterministic spread.
      const angle = parents === 0 ? index * GOLDEN_ANGLE : Math.atan2(sinSum, cosSum);
      return { placedNode: p, angle: ((angle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2) };
    });
    preferred.sort((a, b) => a.angle - b.angle);

    // Each node needs its own label's worth of arc, so a ring of long file
    // names simply sits further out instead of smearing text together.
    const arcs = preferred.map((entry) =>
      Math.max(72, labelHalfWidth(entry.placedNode) * 2 + 14),
    );
    const radius = Math.max(
      innerRadius + RING_GAP,
      arcs.reduce((total, arc) => total + arc, 0) / (Math.PI * 2),
    );

    // Spread the ring by pushing crowded neighbours apart rather than
    // distributing evenly: even spacing looks tidy but drags a node away from
    // the parent it hangs off, which is what draws the long edges across the
    // middle of the picture. Relaxation only moves what actually collides, so
    // a full ring still ends up evenly spaced.
    const widths = arcs.map((arc) => arc / radius);
    for (let pass = 0; pass < 60; pass++) {
      for (let i = 0; i < preferred.length; i++) {
        const j = (i + 1) % preferred.length;
        if (i === j) break; // single node on this ring
        const wrapped = j === 0;
        const gap =
          preferred[j].angle - preferred[i].angle + (wrapped ? Math.PI * 2 : 0);
        const wanted = (widths[i] + widths[j]) / 2;
        if (gap >= wanted) continue;
        const push = (wanted - gap) / 2;
        preferred[i].angle -= push;
        preferred[j].angle += push;
      }
    }

    for (const entry of preferred) {
      const { angle } = entry;
      angles.set(entry.placedNode.node.id, angle);
      entry.placedNode.x = centreX + Math.cos(angle) * radius;
      entry.placedNode.y = centreY + Math.sin(angle) * radius;
    }

    innerRadius = radius;
  }

  if (focus) {
    focus.x = centreX;
    focus.y = centreY;
  }

  // Even arc spacing keeps a ring clear of itself, but two rings can still
  // collide where a wide label on the inner ring reaches outwards.
  for (let pass = 0; pass < 24; pass++) {
    resolveCollisions(placed);
    if (focus) {
      focus.x = centreX;
      focus.y = centreY;
    }
  }

  quantiseLayout(placed);

  return {
    nodes: placed,
    edges: links,
    width,
    height,
    viewBox: contentBounds(placed, width, height),
  };
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

  // Ideal spring length. The canvas-area term alone goes below a node diameter
  // once the graph is dense, which asks the simulation for a spacing the
  // circles physically cannot hold, so floor it against the nodes themselves.
  const area = width * height;
  const meanRadius =
    placed.reduce((total, p) => total + p.radius, 0) / Math.max(1, placed.length);
  const ideal = Math.max(
    Math.sqrt(area / Math.max(1, placed.length)) * 0.62,
    meanRadius * 2.6,
  );
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

    // Repulsion alone is radius-blind, so large nodes still overlap. During the
    // simulation only the circles matter; label spacing is settled after the
    // final scale, when positions stop moving.
    resolveCircleCollisions(placed);

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
  // settle again at the final size — this time accounting for label width,
  // which is what actually has to be readable. Each pass only nudges a
  // colliding pair halfway apart, so a crowded graph needs a good number of
  // them: at 30 a 70-node canvas still finished with circles overlapping.
  for (let pass = 0; pass < 80; pass++) {
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

  quantiseLayout(placed);

  return {
    nodes: placed,
    edges: links,
    width,
    height,
    viewBox: contentBounds(placed, width, height),
  };
}
