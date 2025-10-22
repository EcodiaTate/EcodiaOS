'use client'

import * as THREE from 'three'
import { useMemo } from 'react'

interface Star {
  id: string
  position: [number, number, number]
}

interface Props {
  selected: Star[]
}

export default function ConstellationConnections({ selected }: Props) {
  const lines = useMemo(() => {
    const pairs: { start: THREE.Vector3; mid: THREE.Vector3; end: THREE.Vector3; key: string }[] = []
    selected.forEach((a, i) => {
      selected.slice(i + 1).forEach((b) => {
        const start = new THREE.Vector3(...a.position)
        const end = new THREE.Vector3(...b.position)
        const mid = new THREE.Vector3(
          (a.position[0] + b.position[0]) / 2,
          (a.position[1] + b.position[1]) / 2 + 80,
          (a.position[2] + b.position[2]) / 2
        )
        pairs.push({ start, mid, end, key: `${a.id}-${b.id}` })
      })
    })
    return pairs
  }, [selected])

  return (
    <>
      {lines.map(({ start, mid, end, key }) => {
        const curve = new THREE.CatmullRomCurve3([start, mid, end])
        const points = curve.getPoints(24)
        const geometry = new THREE.BufferGeometry().setFromPoints(points)
        const material = new THREE.LineBasicMaterial({ color: '#f4d35e', transparent: true, opacity: 0.9 })
        return <primitive key={key} object={new THREE.Line(geometry, material)} />
      })}
    </>
  )
}
