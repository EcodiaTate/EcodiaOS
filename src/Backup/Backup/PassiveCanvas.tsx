'use client'

import { Suspense, useRef, useMemo, useEffect } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import EcodiaCore from '@/components/EcodiaCore'

const NUM_NODES = 800
const MAX_CONNECTIONS_PER_NODE = 3
const CONNECTION_RADIUS = 600
const BOUNDS = { x: 500, y: 500, z: 500 }
const PULSE_INTERVAL = 1500
const PULSE_DURATION = 2000

const SYSTEM_TAGS = ["Qora", "Evo", "Atune", "Contra", "Thread", "Ember", "Nova", "Unity"] as const
type System = typeof SYSTEM_TAGS[number]

function getColorForSystem(system: System): string {
  const colorMap: Record<System, string> = {
    Qora: "#f4d35e",
    Evo: "#b388eb",
    Atune: "#5fdde5",
    Contra: "#ff99a3",
    Thread: "#9df59f",
    Ember: "#ff744f",
    Nova: "#ffd6ff",
    Unity: "#78fcae"
  }
  return colorMap[system] || "#ffffff"
}

interface Node {
  position: [number, number, number]
  system: System
}

interface Connection {
  a: number
  b: number
  ref: React.MutableRefObject<THREE.Object3D | null>
  activeUntil: number
}

const nodesRef = { current: [] as Node[] }
const connectionsRef = { current: [] as Connection[] }
const adjacencyMap: Record<number, number[]> = {}
const lastPulseTimeRef = { current: 0 }

function distance(a: [number, number, number], b: [number, number, number]) {
  return Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)
}

function generateNodes(): Node[] {
  return Array.from({ length: NUM_NODES }, () => ({
    position: [
      (Math.random() - 0.5) * BOUNDS.x,
      (Math.random() - 0.5) * BOUNDS.y,
      (Math.random() - 0.5) * BOUNDS.z
    ],
    system: SYSTEM_TAGS[Math.floor(Math.random() * SYSTEM_TAGS.length)]
  }))
}

function generateConnections(nodes: Node[]): Connection[] {
  const result: Connection[] = []
  const connectionCount = Array(nodes.length).fill(0)

  for (let i = 0; i < nodes.length; i++) {
    if (!adjacencyMap[i]) adjacencyMap[i] = []
    for (let j = i + 1; j < nodes.length; j++) {
      if (!adjacencyMap[j]) adjacencyMap[j] = []
      if (connectionCount[i] >= MAX_CONNECTIONS_PER_NODE) break
      if (connectionCount[j] >= MAX_CONNECTIONS_PER_NODE) continue
      if (distance(nodes[i].position, nodes[j].position) < CONNECTION_RADIUS) {
        const ref = { current: null as THREE.Object3D | null }
        result.push({ a: i, b: j, ref, activeUntil: 0 })
        connectionCount[i]++
        connectionCount[j]++
        adjacencyMap[i].push(j)
        adjacencyMap[j].push(i)
      }
    }
  }

  return result
}

function propagatePulse(origin: number, now: number, visited = new Set<number>(), depth = 0) {
  if (visited.has(origin) || depth > 5) return
  visited.add(origin)

  const neighbors = adjacencyMap[origin] || []
  for (const target of neighbors) {
    const edge = connectionsRef.current.find(c =>
      (c.a === origin && c.b === target) || (c.b === origin && c.a === target)
    )
    if (edge) {
      edge.activeUntil = now + PULSE_DURATION
      setTimeout(() => {
        propagatePulse(target, now, visited, depth + 1)
      }, 50)
    }
  }
}

function usePulseManager() {
  useFrame(({ clock }) => {
    const now = clock.getElapsedTime() * 1000
    const last = lastPulseTimeRef.current
    if (Math.floor(now / PULSE_INTERVAL) !== Math.floor(last / PULSE_INTERVAL)) {
      lastPulseTimeRef.current = now
      const origin = Math.floor(Math.random() * nodesRef.current.length)
      propagatePulse(origin, now)
    }
  })
}

function PulseController() {
  usePulseManager()
  return null
}

function BrainNode({ node }: { node: Node }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const randomOffset = useMemo(() => Math.random(), [])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const pulse = 1 + Math.sin(t * 2 + randomOffset) * 0.2
    if (meshRef.current) {
      meshRef.current.scale.set(pulse, pulse, pulse)
    }
  })

  return (
    <mesh ref={meshRef} position={node.position}>
      <sphereGeometry args={[1, 12, 12]} />
      <meshStandardMaterial
        color={getColorForSystem(node.system)}
        emissive={getColorForSystem(node.system)}
        emissiveIntensity={12}
        toneMapped={false}
      />
    </mesh>
  )
}

function CurvedConnectionLine({ connection }: { connection: Connection }) {
  const { a, b, ref } = connection
  const [start, end] = [nodesRef.current[a].position, nodesRef.current[b].position]
  const curve = useMemo(() => new THREE.CatmullRomCurve3([
    new THREE.Vector3(...start),
    new THREE.Vector3(
      (start[0] + end[0]) / 2,
      (start[1] + end[1]) / 2 + 80,
      (start[2] + end[2]) / 2
    ),
    new THREE.Vector3(...end)
  ]), [start, end])

  const points = useMemo(() => curve.getPoints(16), [curve])
  const geometry = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points])
  const color = useMemo(() => new THREE.Color(`hsl(${Math.random() * 360}, 100%, 70%)`), [])
  const material = useMemo(() => new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.1 }), [])

  const line = useMemo(() => new THREE.Line(geometry, material), [geometry, material])

  useEffect(() => {
    ref.current = line
  }, [line])

  useFrame(({ clock }) => {
    const now = clock.getElapsedTime() * 1000
    const timeLeft = connection.activeUntil - now
    line.material.opacity = timeLeft > 0 ? Math.max(0.15, timeLeft / PULSE_DURATION) : 0.1
  })

  return <primitive object={line} ref={ref as any} />
}


function EcodiaBrainCanvas() {
  if (nodesRef.current.length === 0) {
    nodesRef.current = generateNodes()
    connectionsRef.current = generateConnections(nodesRef.current)
  }

  return (
    <Canvas camera={{ position: [0, 0, 4000], fov: 70, near: 0.1, far: 200 }} gl={{ logarithmicDepthBuffer: true }}>
      <ambientLight intensity={0.2} />
      <pointLight position={[0, 80, 100]} intensity={2.8} />
      <PulseController />
      <EcodiaCore />
      {nodesRef.current.map((node, i) => <BrainNode node={node} key={i} />)}
      {connectionsRef.current.map((connection, i) => <CurvedConnectionLine connection={connection} key={i} />)}
      <OrbitControls enablePan enableZoom enableRotate />
    </Canvas>
  )
}

export default function EcodiaMind() {
  return (
    <main className="fixed inset-0 w-screen h-screen m-0 p-0 overflow-hidden bg-black">
      <Suspense fallback={<div className="text-black">Loading cognition...</div>}>
        <EcodiaBrainCanvas />
      </Suspense>
    </main>
  )
}
