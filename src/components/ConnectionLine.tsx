'use client'

import * as THREE from 'three'
import { useMemo, useRef, useEffect } from 'react'
import { useFrame } from '@react-three/fiber'

import vertexShader from '@/shaders/connection.vert'
import fragmentShader from '@/shaders/connection_continuous.frag'
import { PulseConnection, PULSE_DURATION } from '@/lib/graphUtils'

interface Props {
  connection: PulseConnection
  nodesRef: { position: [number, number, number]; isOuter?: boolean; isStar?: boolean }[]
}

const SEGMENTS = 12

export default function ConnectionLine({ connection, nodesRef }: Props) {
  // Skip star-to-star
  if (nodesRef[connection.a]?.isStar && nodesRef[connection.b]?.isStar) {
    return null
  }

  const shaderRef = useRef<THREE.ShaderMaterial | null>(null)
  const lineRef = useRef<THREE.Line | null>(null)

  const isCoreEdge =
    !nodesRef[connection.a]?.isOuter && !nodesRef[connection.b]?.isOuter

  const staticHue = useMemo(() => Math.random(), [])

  const startIndex = connection.a
  const endIndex = connection.b

  const start = useMemo(
    () => new THREE.Vector3(...nodesRef[startIndex].position),
    [startIndex, nodesRef]
  )
  const end = useMemo(
    () => new THREE.Vector3(...nodesRef[endIndex].position),
    [endIndex, nodesRef]
  )

  const curve = useMemo(() => {
    const isOuterA = nodesRef[startIndex]?.isOuter
    const isOuterB = nodesRef[endIndex]?.isOuter
    const isOuterEdge = isOuterA || isOuterB

    const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5)

    if (isOuterEdge) {
      const verticalLift = (Math.random() - 0.5) * 2400
      const horizontalSweep = 200 + Math.random() * 600
      const twist = (Math.random() - 0.5) * 2 * Math.PI

      const offset = new THREE.Vector3(
        Math.sin(twist) * horizontalSweep,
        verticalLift,
        Math.cos(twist) * horizontalSweep
      )

      mid.add(offset)
    } else {
      mid.y += 100 + Math.random() * 50
    }

    return new THREE.QuadraticBezierCurve3(start, mid, end)
  }, [start, end, nodesRef, startIndex, endIndex])

  const points = useMemo(() => curve.getPoints(SEGMENTS), [curve])

  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry().setFromPoints(points)
    const progress = new Float32Array(points.length)
    for (let i = 0; i < points.length; i++) {
      progress[i] = i / (points.length - 1)
    }
    geo.setAttribute('progress', new THREE.BufferAttribute(progress, 1))
    return geo
  }, [points])

  const material = useMemo(() => {
    const color = new THREE.Color().setHSL(
      staticHue,
      1,  
      0.6
    )

    return new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: {
        uColor: { value: color },
        uTime: { value: 0 },
        uActivatedAt: { value: -1 },
        uDuration: { value: PULSE_DURATION },
        uIsCore: { value: isCoreEdge ? 1.0 : 0.0 },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.NormalBlending, // dark-only
      toneMapped: false,
    })
  }, [staticHue, isCoreEdge])

  useEffect(() => {
    shaderRef.current = material
    if (!lineRef.current) {
      lineRef.current = new THREE.Line(geometry, material)
    }
  }, [geometry, material])

  useFrame(({ clock }) => {
    const now = clock.getElapsedTime() * 1000
    if (shaderRef.current) {
      shaderRef.current.uniforms.uTime.value = now
      shaderRef.current.uniforms.uActivatedAt.value = connection.activatedAt ?? -1
      shaderRef.current.needsUpdate = true
    }
  })

  return lineRef.current ? <primitive object={lineRef.current} /> : null
}
