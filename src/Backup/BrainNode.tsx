// src/components/BrainNode.tsx
'use client';

import * as THREE from 'three';
import { useMemo } from 'react';

export default function BrainNode({ node }: { node: { position: [number,number,number], size?: number } }) {
  const material = useMemo(() => new THREE.SpriteMaterial({
    color: new THREE.Color(0x9fe4c6), // minty
    opacity: 0.9,
    depthWrite: false,
    depthTest: true,
    blending: THREE.NormalBlending,
    toneMapped: false,
  }), []);

  const scale = (node.size ?? 60) * 0.035; // tune as needed

  return (
    <sprite position={node.position as any} material={material} scale={[scale, scale, 1]} />
  );
}
