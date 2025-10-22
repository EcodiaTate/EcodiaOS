import * as THREE from 'three'
import { Line2 } from 'three/examples/jsm/lines/Line2'

// === Types ===

export type System =
  | 'Qora' | 'Evo' | 'Atune' | 'Contra'
  | 'Thread' | 'Ember' | 'Nova' | 'Unity'

export interface Star {
  id: string
  position: [number, number, number]
  word: string
  size: number
  glow: number
  isStar?: true
}

export interface Node {
  position: [number, number, number]
  system: System
  isStar?: boolean
  isOuter?: boolean
  word?: string
  id?: string
  size?: number
  glow?: number
}

export interface Connection {
  a: number
  b: number
  ref: React.MutableRefObject<Line2 | null>
  activeUntil: number
  activatedAt?: number
}

export interface PulseConnection extends Connection {
  pendingActivationAt?: number
  id?: string
  isCoreConnection?: boolean
  activatedFrom?: number // ✅ Add this line
}


// === Constants ===

export const SYSTEM_TAGS: System[] = [
  'Qora', 'Evo', 'Atune', 'Contra',
  'Thread', 'Ember', 'Nova', 'Unity',
]

export const NUM_NODES = 400
export const MAX_CONNECTIONS = 3
export const SPHERE_RADIUS = 5000
export const SPHERE_VARIANCE = 0
export const CONNECTION_RADIUS = 2800
export const CONNECTION_RADIUS_BOOST = 1.15

export const PULSE_RISE_MS = 150
export const PULSE_FADE_MS = 150
export const PULSE_DURATION = 250
export const PULSE_MIN_OPACITY = 0.08
export const PULSE_PEAK_OPACITY = 0.6

// === 🌌 Node Generation ===

export function generateNodes(withStars: Star[]): Node[] {
  const core: Node[] = withStars.map(star => ({
    ...star,
    system: 'Unity',
    isStar: true,
    word: star.word ?? '???',
    size: star.size ?? 40 + Math.random() * 20,
    glow: star.glow ?? 5 + Math.random() * 10,
  }))

  const filler: Node[] = Array.from({ length: NUM_NODES - core.length }, () => {
    const r = SPHERE_RADIUS + Math.random() * SPHERE_VARIANCE
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    const x = r * Math.sin(phi) * Math.cos(theta)
    const y = r * Math.sin(phi) * Math.sin(theta)
    const z = r * Math.cos(phi)

    return {
      position: [x, y, z] as [number, number, number],
      system: SYSTEM_TAGS[Math.floor(Math.random() * SYSTEM_TAGS.length)],
      isOuter: true,
    }
  })

  return [...core, ...filler]
}

// === 🔗 Connection Generation ===

export function generateConnections(
  nodes: Node[],
  adjacencyMap: Record<number, number[]>
): PulseConnection[] {
  const result: PulseConnection[] = []
  const count: number[] = Array(nodes.length).fill(0)
  let connId = 0
  const coreIndex = 0

  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      if (count[i] >= MAX_CONNECTIONS || count[j] >= MAX_CONNECTIONS) continue

      const posA = new THREE.Vector3(...nodes[i].position)
      const posB = new THREE.Vector3(...nodes[j].position)
      const dist = posA.distanceTo(posB)

      const bothStars = nodes[i].isStar && nodes[j].isStar
      const radius = bothStars
        ? CONNECTION_RADIUS * CONNECTION_RADIUS_BOOST
        : CONNECTION_RADIUS

      if (dist < radius) {
        const isCoreConnection = i === coreIndex || j === coreIndex
        const ref = { current: null as Line2 | null }

        result.push({
          a: i,
          b: j,
          ref,
          activeUntil: 0,
          id: `conn-${connId++}`,
          isCoreConnection,
        })

        count[i]++
        count[j]++

        adjacencyMap[i] = [...(adjacencyMap[i] || []), j]
        adjacencyMap[j] = [...(adjacencyMap[j] || []), i]
      }
    }
  }

  // === Ensure Arc to Top & Bottom Outer Nodes
  const outerNodes = nodes
    .map((_, i) => i)
    .filter(i => i !== coreIndex && nodes[i].isOuter)

  const arcCount = Math.max(1, Math.floor(nodes.length * 0.1))
  const topY = [...outerNodes].sort((a, b) => nodes[b].position[1] - nodes[a].position[1]).slice(0, arcCount)
  const bottomY = [...outerNodes].sort((a, b) => nodes[a].position[1] - nodes[b].position[1]).slice(0, arcCount)
  const selected = new Set([...topY, ...bottomY])

  for (const i of selected) {
    const already = result.some(conn =>
      (conn.a === coreIndex && conn.b === i) || (conn.b === coreIndex && conn.a === i)
    )
    if (!already) {
      const ref = { current: null as Line2 | null }
      result.push({
        a: coreIndex,
        b: i,
        ref,
        activeUntil: 0,
        id: `conn-${connId++}`,
        isCoreConnection: true,
      })
      adjacencyMap[coreIndex] = [...(adjacencyMap[coreIndex] || []), i]
      adjacencyMap[i] = [...(adjacencyMap[i] || []), coreIndex]
    }
  }

  return result
}
