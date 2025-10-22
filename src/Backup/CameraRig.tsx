'use client'

import { useEffect, useRef } from 'react'
import { useThree } from '@react-three/fiber'
import { useModeStore } from '@/stores/useModeStore'
import * as THREE from 'three'
import { OrbitControls as OrbitControlsImpl } from 'three-stdlib'

export default function CameraRig() {
  const { camera, controls: rawControls } = useThree()
  const controls = rawControls as unknown as OrbitControlsImpl
  const target = useModeStore((s) => s.targetCamera)
  const isConstellation = useModeStore((s) => s.mode === 'constellation')

  const animRef = useRef<number>()

  useEffect(() => {
  if (!controls) return

  cancelAnimationFrame(animRef.current!)

  const currentOffset = new THREE.Vector3().subVectors(camera.position, controls.target)
  const spherical = new THREE.Spherical().setFromVector3(currentOffset)

  const currentRadius = spherical.radius

  const newTarget = new THREE.Vector3(...target.lookAt)
  const targetRadius = new THREE.Vector3(...target.position).sub(newTarget).length()

  // keep orbit angles, just animate radius
  const start = performance.now()
  const duration = 500 // ms

  const animate = (now: number) => {
    const t = Math.min((now - start) / duration, 1)
    const eased = t < 1 ? 1 - Math.pow(1 - t, 3) : 1

    spherical.radius = THREE.MathUtils.lerp(currentRadius, targetRadius, eased)
    const newOffset = new THREE.Vector3().setFromSpherical(spherical)

    camera.position.copy(newTarget.clone().add(newOffset))

    // Only update OrbitControls target if not in constellation mode
    if (!isConstellation) {
      controls.target.copy(newTarget)
    }

    controls.update()

    if (t < 1) animRef.current = requestAnimationFrame(animate)
  }

  animRef.current = requestAnimationFrame(animate)
}, [target, isConstellation, camera, controls])

  return null
}
