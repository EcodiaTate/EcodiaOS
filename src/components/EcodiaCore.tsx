'use client'

import * as THREE from 'three'
import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { useVoiceStore } from '@/stores/useVoiceStore'; // <-- Add this import

const NUM_LAYERS = 10
const BASE_RADIUS = 48
const RADIUS_STEP = 14
const BASE_OPACITY = 0.85
const OPACITY_FALLOFF = 0.06 // exponential-ish falloff factor per layer

export default function EcodiaCore() {
  const groupRef = useRef<THREE.Group>(null)
  const coreMatRef = useRef<THREE.MeshStandardMaterial>(null)
  const haloRefs = useRef<Array<{ mesh: THREE.Mesh; mat: THREE.MeshBasicMaterial }>>([])
  
  const isPlaying = useVoiceStore((s) => s.isPlaying); // <-- Listen to the voice state


  const reduceMotion =
    typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  // Shared high-res sphere (we’ll scale per layer)
  const sphereGeo = useMemo(() => new THREE.SphereGeometry(1, 64, 64), [])

  // Prebuild radii & base opacities
  const layers = useMemo(() => {
    return Array.from({ length: NUM_LAYERS }, (_, i) => {
      const radius = BASE_RADIUS + i * RADIUS_STEP
      // exponential-ish decay: base * e^(-i*falloff)
      const opacity = BASE_OPACITY * Math.exp(-i * OPACITY_FALLOFF)
      return { radius, opacity }
    })
  }, [])

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const speed = 1; // Simplified speed

    // --- Voice-driven animation ---
    // When speaking, the core pulses more rapidly and intensely.
    const basePulseFreq = isPlaying ? 3.5 : 0.7;
    const basePulseAmp = isPlaying ? 0.08 : 0.04;
    const scalePulse = 1 + Math.sin(t * basePulseFreq) * basePulseAmp;
    if (groupRef.current) groupRef.current.scale.set(scalePulse, scalePulse, scalePulse)

    // Brand hue sweep (unchanged)
    const hue = 0.16 + (Math.sin(t * 0.25) * 0.5 + 0.5) * (0.28 - 0.16);
    const coreColor = new THREE.Color().setHSL(hue, 0.8, 0.55);
    const haloColor = new THREE.Color().setHSL(hue, 0.85, 0.60);

    // Core emissive pulse is also intensified by speech
    const baseEmissive = isPlaying ? 2.5 : 1.6;
    const emissivePulseAmp = isPlaying ? 0.6 : 0.25;
    if (coreMatRef.current) {
      coreMatRef.current.emissive.copy(coreColor)
      coreMatRef.current.emissiveIntensity = baseEmissive + Math.sin(t * (basePulseFreq * 2)) * emissivePulseAmp;
    }

    // Halos breathe opacity slightly (unchanged)
    for (const { mat } of haloRefs.current) {
      const base = mat.userData._baseOpacity as number
      const wiggle = (Math.sin(t * 1.1) * 0.04)
      mat.opacity = THREE.MathUtils.clamp(base + wiggle, 0.05, 0.5)
      mat.color.copy(haloColor)
    }
  })
  
  // Ensure refs array matches layer count
  haloRefs.current = []

  return (
    <group ref={groupRef} position={[0, 0, 0]}>
      {/* Inner core: solid, emissive, subtle metal for specular hints */}
      <mesh>
        <primitive object={sphereGeo} attach="geometry" />
        <meshStandardMaterial
          ref={coreMatRef}
          color={'#0e1410'}
          emissive={'#F4D35E'}
          emissiveIntensity={1.8}
          roughness={0.2}
          metalness={0.25}
          toneMapped={false}
        />
      </mesh>

      {/* Concentric additive halos */}
      {layers.map(({ radius, opacity }, i) => (
        <mesh
          key={i}
          scale={[radius, radius, radius]}
          renderOrder={-1}
        >
          <primitive object={sphereGeo} attach="geometry" />
          <meshBasicMaterial
            ref={(mat) => {
              if (!mat) return
              // store for animation updates
              const parent = (mat as any).__mesh as THREE.Mesh | undefined
              haloRefs.current[i] = { mesh: parent || ({} as any), mat }
              mat.userData._baseOpacity = opacity
            }}
            color={'#F4D35E'}
            transparent
            opacity={opacity}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            side={THREE.FrontSide}
            toneMapped={false}
          />
        </mesh>
      ))}
    </group>
  )
}
