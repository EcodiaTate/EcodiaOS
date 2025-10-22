'use client'

import * as THREE from 'three'
import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'

interface ConstellationStarProps {
  star: {
    id: string
    position: [number, number, number]
    word: string
    size: number
    glow: number
  }
  isSelected: boolean
  onClick: () => void
}

/** Deterministic 0..1 hash from a string (for stable twinkle phase) */
function hash01(key: string) {
  let h = 2166136261 >>> 0
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  h += h << 13; h ^= h >>> 7; h += h << 3; h ^= h >>> 17; h += h << 5
  return (h >>> 0) / 4294967295
}

export default function ConstellationStar({ star, isSelected, onClick }: ConstellationStarProps) {
  const coreRef = useRef<THREE.Mesh>(null)
  const auraRef = useRef<THREE.Mesh>(null)
  const matRef  = useRef<THREE.MeshStandardMaterial>(null)

  const reduceMotion =
    typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  // Stable per-star phase so the twinkle isn't in lockstep
  const phase = useMemo(() => hash01(star.id) * Math.PI * 2, [star.id])

  // Sizes
  const baseRadius = star.size // you’re already passing world-sized stars (e.g. 50–80)
  const selectedScale = 1.5
  const auraScaleBase = 1.35
  const auraScaleSelected = 1.75

  // Colors
  const bodyColor = useMemo(() => new THREE.Color('#e9f4ec'), [])
  const selectedGlow = useMemo(() => new THREE.Color('#F4D35E'), [])
  const idleGlow = useMemo(() => new THREE.Color('#cfe9d6'), []) // subtle minty white for dark sky
  const auraColor = isSelected ? selectedGlow : idleGlow

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const speed = reduceMotion ? 0 : 1.4
    const amp   = isSelected ? 0.12 : 0.06

    // Gentle size twinkle
    const s = speed === 0 ? 1 : 1 + Math.sin(t * speed + phase) * amp

    // Emissive breathing (a tad stronger when selected)
    const baseEmissive = isSelected ? 2.2 : 1.2
    const emissivePulse = speed === 0 ? baseEmissive : baseEmissive + Math.sin(t * (speed * 0.9) + phase) * 0.2

    if (coreRef.current) {
      coreRef.current.scale.set(s, s, s)
    }
    if (matRef.current) {
      matRef.current.emissiveIntensity = emissivePulse
    }
    if (auraRef.current) {
      const aScale = (isSelected ? auraScaleSelected : auraScaleBase) * s
      auraRef.current.scale.set(aScale, aScale, aScale)
      const m = auraRef.current.material as THREE.MeshBasicMaterial
      // keep aura within a tasteful range
      const target = isSelected ? 0.22 : 0.12
      m.opacity = reduceMotion ? target : THREE.MathUtils.clamp(target + Math.sin(t * (speed * 0.8) + phase) * 0.04, 0.06, 0.25)
    }
  })

  return (
    <group
      position={star.position}
      onPointerDown={(e) => { e.stopPropagation(); onClick() }}
      onPointerOver={() => { document.body.style.cursor = 'pointer' }}
      onPointerOut={() => { document.body.style.cursor = 'auto' }}
    >
      {/* Core star */}
      <mesh ref={coreRef}>
        <sphereGeometry args={[baseRadius * (isSelected ? selectedScale : 1), 24, 24]} />
        <meshStandardMaterial
          ref={matRef}
          color={bodyColor}
          emissive={isSelected ? selectedGlow : idleGlow}
          emissiveIntensity={isSelected ? 2.2 : 1.2}
          roughness={0.25}
          metalness={0.2}
          toneMapped={false}
        />
      </mesh>

      {/* Soft additive aura halo */}
      <mesh ref={auraRef} renderOrder={-1}>
        <sphereGeometry args={[baseRadius, 24, 24]} />
        <meshBasicMaterial
          color={auraColor}
          transparent
          opacity={isSelected ? 0.22 : 0.12}
          blending={THREE.AdditiveBlending}
          depthWrite={false}
          toneMapped={false}
        />
      </mesh>
    </group>
  )
}
