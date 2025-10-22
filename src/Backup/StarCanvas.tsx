'use client'

import { useRef, useState, useEffect, useMemo } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { useRouter } from 'next/navigation'
import EcodiaCore from '@/components/EcodiaCore'

// === Soul Soul Words ===
const PLACEHOLDER_WORDS: string[] = [/* same 100 words as before */]

// === Types ===
interface Star {
  id: string
  position: [number, number, number]
  word: string
  size: number
  glow: number
}

const SYSTEM_TAGS = ["Qora", "Evo", "Atune", "Contra", "Thread", "Ember", "Nova", "Unity"] as const
type System = typeof SYSTEM_TAGS[number]

function getColorForSystem(system: System): string {
  const colorMap: Record<System, string> = {
    Qora: "#f4d35e", Evo: "#b388eb", Atune: "#5fdde5", Contra: "#ff99a3",
    Thread: "#9df59f", Ember: "#ff744f", Nova: "#ffd6ff", Unity: "#78fcae"
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
  ref: React.MutableRefObject<THREE.Line | null>
  activeUntil: number
}

// === Exo Canvas Constants ===
const NUM_NODES = 300
const MAX_CONNECTIONS_PER_NODE = 3
const CONNECTION_RADIUS = 600
const BOUNDS = { x: 3000, y: 3000, z: 3000 }
const PULSE_INTERVAL = 1500
const PULSE_DURATION = 2000

// === Global Data ===
let nodesRef: Node[] = []
let connectionsRef: Connection[] = []
let adjacencyMap: Record<number, number[]> = {}
let lastPulseTime = 0

function generateNodes(): Node[] {
  return Array.from({ length: NUM_NODES }, () => ({
    position: [(Math.random() - 0.5) * BOUNDS.x, (Math.random() - 0.5) * BOUNDS.y, (Math.random() - 0.5) * BOUNDS.z],
    system: SYSTEM_TAGS[Math.floor(Math.random() * SYSTEM_TAGS.length)]
  }))
}

function generateConnections(nodes: Node[]): Connection[] {
  const result: Connection[] = []
  const connectionCount = Array(nodes.length).fill(0)
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      if (connectionCount[i] >= MAX_CONNECTIONS_PER_NODE || connectionCount[j] >= MAX_CONNECTIONS_PER_NODE) continue
      if (new THREE.Vector3(...nodes[i].position).distanceTo(new THREE.Vector3(...nodes[j].position)) < CONNECTION_RADIUS) {
        const ref = { current: null as THREE.Line | null }
        result.push({ a: i, b: j, ref, activeUntil: 0 })
        connectionCount[i]++
        connectionCount[j]++
        adjacencyMap[i] = [...(adjacencyMap[i] || []), j]
        adjacencyMap[j] = [...(adjacencyMap[j] || []), i]
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
    const edge = connectionsRef.find(c =>
      (c.a === origin && c.b === target) || (c.b === origin && c.a === target)
    )
    if (edge) {
      edge.activeUntil = now + PULSE_DURATION
      setTimeout(() => propagatePulse(target, now, visited, depth + 1), 50)
    }
  }
}

// === Canvas Components ===
function ForgeStar({ star, isSelected, onClick }: { star: Star; isSelected: boolean; onClick: () => void }) {
  const meshRef = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const pulse = 1 + Math.sin(t * 2) * 0.15
    meshRef.current?.scale.set(pulse, pulse, pulse)
  })

  return (
    <mesh ref={meshRef} position={star.position} onClick={onClick}>
  <sphereGeometry args={[star.size / 3, 16, 16]} />
  <meshStandardMaterial
    color={isSelected ? '#f4d35e' : '#ffffff'}
    emissive={isSelected ? '#f4d35e' : '#ffffff'}
    emissiveIntensity={isSelected ? 6 : 2}
    toneMapped={false}
  />
  {isSelected && (
    <mesh scale={[1.8, 1.8, 1.8]}>
      <sphereGeometry args={[star.size / 2 + 1.5, 16, 16]} />
      <meshStandardMaterial
        color={'#f4d35e'}
        transparent
        opacity={1}
        emissive={'#f4d35e'}
        emissiveIntensity={1}
      />
    </mesh>
  )}
</mesh>

  )
}

function CurvedConnections({ selected }: { selected: Star[] }) {
  return (
    <>
      {selected.map((a, i) =>
        selected.slice(i + 1).map((b) => {
          const curve = new THREE.CatmullRomCurve3([
            new THREE.Vector3(...a.position),
            new THREE.Vector3(
              (a.position[0] + b.position[0]) / 2,
              (a.position[1] + b.position[1]) / 2 + 80,
              (a.position[2] + b.position[2]) / 2
            ),
            new THREE.Vector3(...b.position),
          ])
          const points = curve.getPoints(16)
          const geometry = new THREE.BufferGeometry().setFromPoints(points)
          return (
            <primitive
              key={`${a.id}-${b.id}`}
              object={new THREE.Line(geometry, new THREE.LineBasicMaterial({ color: '#f4d35e' }))}
            />
          )
        })
      )}
    </>
  )
}

function BrainNode({ node }: { node: Node }) {
  const meshRef = useRef<THREE.Mesh>(null)
  const randomOffset = useMemo(() => Math.random(), [])
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const pulse = 1 + Math.sin(t * 2 + randomOffset) * 0.2
    meshRef.current?.scale.set(pulse, pulse, pulse)
  })

  return (
    <mesh ref={meshRef} position={node.position}>
      <sphereGeometry args={[1, 12, 12]} />
      <meshStandardMaterial
        color="#333344"
        emissive="#333344"
        emissiveIntensity={2}
        toneMapped={false}
      />
    </mesh>
  )
}

function ConnectionLine({ connection }: { connection: Connection }) {
  const { a, b, ref } = connection
  const [start, end] = [nodesRef[a].position, nodesRef[b].position]
  const points = [new THREE.Vector3(...start), new THREE.Vector3(...end)]
  const geometry = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [])
  const color = useMemo(() => new THREE.Color(`hsl(${Math.random() * 360}, 100%, 70%)`), [])
  const material = useRef(new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.05 }))

  useFrame(({ clock }) => {
    const now = clock.getElapsedTime() * 1000
    const mat = ref.current?.material as THREE.LineBasicMaterial
    const timeLeft = connection.activeUntil - now
    if (mat) mat.opacity = timeLeft > 0 ? Math.max(0.15, timeLeft / PULSE_DURATION) : 0.05
  })

  return <primitive object={new THREE.Line(geometry, material.current)} ref={ref} />
}

function PulseManager() {
  useFrame(({ clock }) => {
    const now = clock.getElapsedTime() * 1000
    if (Math.floor(now / PULSE_INTERVAL) !== Math.floor(lastPulseTime / PULSE_INTERVAL)) {
      lastPulseTime = now
      const origin = Math.floor(Math.random() * nodesRef.length)
      propagatePulse(origin, now)
    }
  })
  return null
}

// === Main Component ===
export default function ForgeCanvas({ onComplete, totalStars = 10 }: { onComplete: (words: string[]) => void; totalStars?: number }) {
  const [stars, setStars] = useState<Star[]>([])
  const [selected, setSelected] = useState<Star[]>([])
  const [orbitEnabled, setOrbitEnabled] = useState(false)
  const router = useRouter()

  useEffect(() => {
    setStars(Array.from({ length: 100 }).map((_, i) => ({
      id: `star-${i}`,
      position: [(Math.random() - 0.5) * 1200, (Math.random() - 0.5) * 1200, (Math.random() - 0.5) * 1200],
      word: PLACEHOLDER_WORDS[i],
      size: Math.random() * 3 + 20,
      glow: Math.random() * 10 + 5,
    })))
    nodesRef = generateNodes()
    connectionsRef = generateConnections(nodesRef)
  }, [])

  useEffect(() => {
    let timeout = setTimeout(() => setOrbitEnabled(true), 5000)
    const reset = () => {
      setOrbitEnabled(false)
      clearTimeout(timeout)
      timeout = setTimeout(() => setOrbitEnabled(true), 5000)
    }
    window.addEventListener('mousedown', reset)
    window.addEventListener('keydown', reset)
    return () => {
      window.removeEventListener('mousedown', reset)
      window.removeEventListener('keydown', reset)
    }
  }, [])

  const handleSelect = (star: Star) => {
    const exists = selected.find(s => s.id === star.id)
    if (exists) setSelected(selected.filter(s => s.id !== star.id))
    else if (selected.length < totalStars) setSelected([...selected, star])
  }

  const handleFinalize = () => {
    const words = selected.map(s => s.word)
    localStorage.setItem('soulNode', JSON.stringify(words))
    onComplete(words)
    router.push('/soul')
  }

  return (
    <div className="relative w-full h-screen">
      <Canvas camera={{ position: [0, 0, 1000], fov: 65, near: 0.1, far: 8000 }} gl={{ logarithmicDepthBuffer: true }}>
        <ambientLight intensity={0.3} />
        <pointLight position={[100, 100, 100]} intensity={2.5} />
        <OrbitControls autoRotate={orbitEnabled} enablePan enableZoom enableRotate />
        <PulseManager />
        <EcodiaCore />
        {stars.map((star) => (
          <ForgeStar key={star.id} star={star} isSelected={selected.some((s) => s.id === star.id)} onClick={() => handleSelect(star)} />
        ))}
        <CurvedConnections selected={selected} />
        {nodesRef.map((node, i) => <BrainNode node={node} key={i} />)}
        {connectionsRef.map((connection, i) => <ConnectionLine connection={connection} key={i} />)}
      </Canvas>

      <div className="absolute top-5 left-5 text-black text-sm font-mono z-10">
        {selected.length} / {totalStars} selected
      </div>

      {selected.length === totalStars && (
        <div className="absolute bottom-10 left-1/2 -translate-x-1/2 z-10">
          <button onClick={handleFinalize} className="bg-white text-black px-6 py-2 rounded-md shadow-md">
            Forge Soul
          </button>
        </div>
      )}
    </div>
  )
}
