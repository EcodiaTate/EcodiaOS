// src/components/FlowController.tsx
'use client';

import { useFrame } from '@react-three/fiber';
import { useMemo, useRef } from 'react';
import { useVoiceStore } from '@/stores/useVoiceStore';
import { PulseConnection, PULSE_DURATION, PULSE_RISE_MS } from '@/lib/graphUtils';

type NodeRef = { position: [number, number, number]; isOuter?: boolean; isHub?: boolean };
type Adjacency = Record<number, number[]>;

interface Props {
  nodesRef: NodeRef[];
  connectionsRef: PulseConnection[];
  adjacencyMap: Adjacency;
  /** average ms between seed bursts when idle */
  baseIntervalMs?: number;         // default 900
  /** how many starting seeds per burst (idle) */
  baseSeedsPerBurst?: number;      // default 2
  /** max BFS depth for a chain */
  maxDepth?: number;               // default 14
  /** max branches from each hop */
  maxBranches?: number;            // default 2
}

/** Simple stable hash (0..1) for per-node randomness */
function hash01(i: number) {
  let x = (i + 1) * 2654435761;
  x ^= x << 13; x ^= x >>> 17; x ^= x << 5;
  return (x >>> 0) / 4294967295;
}

/** Lookup a connection for (a,b) regardless of order */
function getEdge(conns: PulseConnection[], a: number, b: number) {
  return conns.find((e) => (e.a === a && e.b === b) || (e.a === b && e.b === a));
}

export default function FlowController({
  nodesRef,
  connectionsRef,
  adjacencyMap,
  baseIntervalMs = 900,
  baseSeedsPerBurst = 2,
  maxDepth = 14,
  maxBranches = 2,
}: Props) {
  const isPlaying = useVoiceStore((s) => s.isPlaying);

  // Frame-scheduled queue (no setTimeout)
  type Event = { edge: PulseConnection; fromNode: number; depth: number; triggerAt: number };
  const queue = useRef<Event[]>([]);
  const active = useRef<Set<PulseConnection>>(new Set());
  const lastBurstAt = useRef(0);

  // Candidate hubs (prefer explicit isHub, else inner nodes)
  const hubIndices = useMemo(() => {
    const hubs: number[] = [];
    for (let i = 0; i < nodesRef.length; i++) {
      const n = nodesRef[i];
      if (n?.isHub) hubs.push(i);
    }
    if (hubs.length) return hubs;
    // fallback: prefer non-outer nodes as “community hubs”
    for (let i = 0; i < nodesRef.length; i++) {
      if (!nodesRef[i]?.isOuter) hubs.push(i);
    }
    // still empty? everyone’s fair game
    return hubs.length ? hubs : nodesRef.map((_, i) => i);
  }, [nodesRef]);

  // Helper to enqueue a propagation step
  const enqueue = (edge: PulseConnection, fromNode: number, depth: number, when: number) => {
    queue.current.push({ edge, fromNode, depth, triggerAt: when });
  };

  // Seed a burst from multiple hubs or random nodes
  const seedBurst = (now: number) => {
    const playingBoost = isPlaying ? 1 : 0;
    const seeds = baseSeedsPerBurst + playingBoost; // 2→3 while speaking
    for (let s = 0; s < seeds; s++) {
      // pick a random hub (biased by hash)
      const pick = Math.floor(hash01((now * 0.001 + s) | 0) * hubIndices.length);
      const startNode = hubIndices[(pick + s) % hubIndices.length];
      const nbrs = adjacencyMap[startNode] || [];
      if (nbrs.length === 0) continue;

      // choose 1–2 outgoing starters
      const starters = Math.min(2, nbrs.length);
      for (let k = 0; k < starters; k++) {
        const nIdx = (k + Math.floor(Math.random() * nbrs.length)) % nbrs.length;
        const neighbor = nbrs[nIdx];
        const edge = getEdge(connectionsRef, startNode, neighbor);
        if (!edge) continue;
        // small jitter so seeds don’t all fire simultaneously
        const jitter = (k * 35) + Math.random() * 80;
        enqueue(edge, startNode, 0, now + jitter);
      }
    }
    lastBurstAt.current = now;
  };

  useFrame(() => {
    const now = performance.now();

    // Adaptive interval: faster when speaking
    const interval = isPlaying ? Math.max(320, baseIntervalMs * 0.55) : baseIntervalMs;

    if (now - lastBurstAt.current > interval) {
      seedBurst(now);
    }

    // Process due events
    // NOTE: process in small batches to avoid spikes
    // eslint-disable-next-line no-constant-condition
    for (let iter = 0; iter < 64; iter++) {
      const idx = queue.current.findIndex((e) => e.triggerAt <= now);
      if (idx === -1) break;
      const evt = queue.current.splice(idx, 1)[0];

      const { edge, fromNode, depth } = evt;
      if (!edge || active.current.has(edge)) continue;

      // Activate the edge
      edge.activatedAt = now;
      edge.activatedFrom = fromNode;
      active.current.add(edge);

      // Deactivate after duration (tracked passively by consumers)
      // We don’t need a timer; consumers use activatedAt vs now.
      // But we can prune active set lazily:
      // (here we keep it until we branch; cheap enough)

      // Propagate outward if depth allows
      if (depth < maxDepth) {
        const nextFrom = edge.a === fromNode ? edge.b : edge.a;
        const neighbors = adjacencyMap[nextFrom] || [];

        // Adaptive branching: +1 possible branch while speaking
        const branchCap = Math.min(
          maxBranches + (isPlaying ? 1 : 0),
          Math.max(1, neighbors.length)
        );

        let branches = 0;
        // Shuffle-ish iteration for variety
        const start = Math.floor(Math.random() * (neighbors.length || 1));
        for (let i = 0; i < neighbors.length && branches < branchCap; i++) {
          const nb = neighbors[(start + i) % neighbors.length];
          // Avoid immediate backtracking into the same edge
          if (nb === fromNode) continue;

          const nextEdge = getEdge(connectionsRef, nextFrom, nb);
          if (!nextEdge || active.current.has(nextEdge)) continue;

          // tiny rising delay
          const delay = Math.min(PULSE_RISE_MS, 28) + Math.random() * 24;
          enqueue(nextEdge, nextFrom, depth + 1, now + delay);
          branches++;
        }
      }

      // Lazy cleanup of expired actives
      if (active.current.size) {
        for (const e of active.current) {
          if (now - (e.activatedAt ?? 0) > PULSE_DURATION) active.current.delete(e);
        }
      }
    }
  });

  return null;
}
