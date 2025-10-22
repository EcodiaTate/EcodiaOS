'use client'

import { useFrame } from '@react-three/fiber'
import { useRef } from 'react'
import {
  PulseConnection,
  PULSE_DURATION,
  PULSE_RISE_MS,
} from '@/lib/graphUtils'

interface PulseControllerProps {
  nodesRef: { position: [number, number, number]; isOuter?: boolean }[]
  connectionsRef: PulseConnection[]
  adjacencyMap: Record<number, number[]>
}

const CORE_INDEX = 0
const PULSE_INTERVAL = 400
const MAX_CHAIN_DEPTH = 20

export default function PulseController({
  nodesRef,
  connectionsRef,
  adjacencyMap,
}: PulseControllerProps) {
  const active = useRef<Set<PulseConnection>>(new Set())
  const queued = useRef<Set<PulseConnection>>(new Set())
  const lastChainStart = useRef(0)
  const hasStarted = useRef(false)

  const activateEdge = (
    edge: PulseConnection,
    now: number,
    depth: number,
    fromNode?: number
  ) => {
    if (!edge || active.current.has(edge)) return

    edge.activatedAt = now
    edge.activatedFrom = fromNode ?? edge.a // 💡 Store direction
    active.current.add(edge)
    queued.current.delete(edge)

    setTimeout(() => {
      active.current.delete(edge)
    }, PULSE_DURATION)

    if (depth < MAX_CHAIN_DEPTH) {
      const from = edge.a === fromNode ? edge.b : edge.a // propagate outward
      const neighbors = adjacencyMap[from] || []

      const MAX_BRANCHES = 3
let branches = 0

for (const neighbor of neighbors) {
  if (branches >= MAX_BRANCHES) break

  const nextEdge = connectionsRef.find(
    (e) =>
      !active.current.has(e) &&
      !queued.current.has(e) &&
      ((e.a === from && e.b === neighbor) ||
        (e.b === from && e.a === neighbor))
  )

  if (nextEdge) {
    const delay = Math.min(PULSE_RISE_MS, 20)
    queued.current.add(nextEdge)

    setTimeout(() => {
      activateEdge(nextEdge, performance.now(), depth + 1, from)
    }, delay)

    branches++ // ✅ propagate to multiple edges!
  }
}
    }
  }

  useFrame(() => {
    const now = performance.now()

    if (!hasStarted.current || now - lastChainStart.current > PULSE_INTERVAL) {
      hasStarted.current = true
      lastChainStart.current = now

      const coreEdges = connectionsRef.filter(
        (e) => e.a === CORE_INDEX || e.b === CORE_INDEX
      )

      if (coreEdges.length > 0) {
        const firstEdge = coreEdges[Math.floor(Math.random() * coreEdges.length)]
        const fromNode = firstEdge.a === CORE_INDEX ? firstEdge.a : firstEdge.b
        activateEdge(firstEdge, now, 0, fromNode)
      }
    }
  })

  return null
}
