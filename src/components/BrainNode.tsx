'use client'

import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { systemColorsDark, systemColorsLight, System } from '@/lib/systemColors'
import { useThemeStore } from '@/stores/useThemeStore'

interface Node {
  position: [number, number, number]
  system: System
  isWordNode?: boolean
  word?: string
}

interface BrainNodeProps {
  node: Node
  highlight?: boolean
}

export default function BrainNode({ node, highlight = false }: BrainNodeProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const theme = useThemeStore(s => s.theme)
  const isLight = theme === 'light'

  const systemColors = isLight ? systemColorsLight : systemColorsDark
  const baseColor = systemColors[node.system] || '#444444'
  const emissiveColor = highlight ? '#f4d35e' : baseColor

  const randomOffset = useMemo(() => Math.random() * Math.PI * 2, [])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const pulse = 1 + Math.sin(t * 2 + randomOffset) * 0.12

    if (meshRef.current) {
      meshRef.current.scale.set(pulse, pulse, pulse)
    }
  })

  return (
    <mesh ref={meshRef} position={node.position}>
      <sphereGeometry args={[node.isWordNode ? 1.5 : 6, 32, 32]} />
      <meshStandardMaterial
        color="#1b1b1b"
        emissive={new THREE.Color(emissiveColor)}
        emissiveIntensity={highlight ? 5 : 2.2}
        roughness={0.15}
        metalness={0.4}
        toneMapped={false}
      />
    </mesh>
  )
}
