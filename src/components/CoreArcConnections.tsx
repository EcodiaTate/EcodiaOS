'use client'

import * as THREE from 'three'
import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { PulseConnection, PULSE_DURATION } from '@/lib/graphUtils'

import vertexShader from '@/shaders/connection.vert'
import fragmentShader from '@/shaders/connection_continuous.frag'

interface Node {
  position: [number, number, number]
  isOuter?: boolean
}

interface Edge {
  source: number
  target: number
  type: 'symbolic' | 'literal'
}

interface Props {
  nodes: Node[]
  edges: Edge[]
  coreIndex: number
  connectionsRef: PulseConnection[]
}

const SEGMENTS = 12
const PINCH = 0.1
const STRETCH_Y = 4500

export default function CoreArcConnections({
  nodes,
  edges,
  coreIndex,
  connectionsRef,
}: Props) {
  const shaderRefs = useRef<THREE.ShaderMaterial[]>([])

  const lines = useMemo(() => {
    const results: {
      line: THREE.Line
      shader: THREE.ShaderMaterial
      conn: PulseConnection | undefined
    }[] = []

    const corePos = new THREE.Vector3(...nodes[coreIndex].position)

    edges.forEach((edge) => {
      const src = nodes[edge.source]
      const tgt = nodes[edge.target]
      if (!src || !tgt) return

      const sourcePos = new THREE.Vector3(...src.position)
      const targetPos = new THREE.Vector3(...tgt.position)

      const sourceDist = sourcePos.length()
      const targetDist = targetPos.length()
      const flipProgress = sourceDist > targetDist ? 1.0 : 0.0

      const from = flipProgress === 1.0 ? targetPos : sourcePos
      const to = flipProgress === 1.0 ? sourcePos : targetPos

      const delta = new THREE.Vector3().subVectors(to, from)
      const dir = delta.y > 0 ? 1 : -1

      const mid = new THREE.Vector3().copy(from)
      mid.x += delta.x * PINCH
      mid.z += delta.z * PINCH
      mid.y += dir * STRETCH_Y

      const curve = new THREE.QuadraticBezierCurve3(from, mid, to)
      const points = curve.getPoints(SEGMENTS)

      const invalid = points.some(
        (p) => !Number.isFinite(p.x) || !Number.isFinite(p.y) || !Number.isFinite(p.z)
      )
      if (invalid) return

      const geometry = new THREE.BufferGeometry().setFromPoints(points)

      const progress = new Float32Array(points.length)
      for (let i = 0; i < points.length; i++) {
        progress[i] = i / (points.length - 1)
      }
      geometry.setAttribute('progress', new THREE.BufferAttribute(progress, 1))

      const hue = Math.random()
      const color = new THREE.Color().setHSL(
        hue,
        0.8,                              // (dark path)
        0.5 + Math.random() * 0.2         // (dark path)
      )

      const material = new THREE.ShaderMaterial({
        vertexShader,
        fragmentShader,
        transparent: true,
        uniforms: {
          uTime: { value: 0 },
          uActivatedAt: { value: -1000 },
          uDuration: { value: PULSE_DURATION },
          uColor: { value: color },
          uIsCore: { value: 1.0 },
          uFlipProgress: { value: flipProgress },
        },
        depthWrite: false,
        blending: THREE.AdditiveBlending,  // (dark path)
      })

      const conn = connectionsRef.find(
        (c) =>
          (c.a === edge.source && c.b === edge.target) ||
          (c.b === edge.source && c.a === edge.target)
      )

      material.uniforms.uActivatedAt.value = conn?.activatedAt ?? -1000
      shaderRefs.current.push(material)

      results.push({
        line: new THREE.Line(geometry, material),
        shader: material,
        conn,
      })
    })

    return results
  }, [nodes, edges, coreIndex, connectionsRef])

  useFrame(({ clock }) => {
    const now = clock.getElapsedTime() * 1000
    lines.forEach(({ shader, conn }) => {
      shader.uniforms.uTime.value = now
      shader.uniforms.uActivatedAt.value = conn?.activatedAt ?? -1000
      shader.needsUpdate = true
    })
  })

  return (
    <>
      <mesh position={nodes[coreIndex].position}>
        <sphereGeometry args={[100, 24, 24]} />
        <meshBasicMaterial color="white" />
      </mesh>

      {lines.map(({ line }, i) => (
        <primitive key={`coreline-${i}`} object={line} />
      ))}
    </>
  )
}
