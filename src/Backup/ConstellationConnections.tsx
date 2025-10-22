// src/components/ConstellationConnections.tsx
'use client';

import * as THREE from 'three';
import { useEffect, useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import vertexShader from '@/shaders/connection.vert';
import fragmentShader from '@/shaders/connection.frag'; // supportive frag

type Star = { id: string; position: [number, number, number] };

type Props = {
  selected: Star[];
  theme?: number; // 0..1
  tint?: THREE.Color | string | number;
};

const SEGMENTS = 20;

export default function ConstellationConnections({
  selected,
  theme = 0.35,
  tint = 0xdaf3e6,
}: Props) {
  const groupRef = useRef<THREE.Group | null>(null);
  const materialRef = useRef<THREE.ShaderMaterial | null>(null);

  const geometries = useMemo(() => {
    const geos: THREE.BufferGeometry[] = [];
    if (selected.length < 2) return geos;

    for (let i = 0; i < selected.length; i++) {
      for (let j = i + 1; j < selected.length; j++) {
        const a = new THREE.Vector3(...selected[i].position);
        const b = new THREE.Vector3(...selected[j].position);
        const mid = a.clone().lerp(b, 0.5);

        const span = a.distanceTo(b);
        const up = 0.06 * span; // gentle arch
        mid.y += up;

        const curve = new THREE.QuadraticBezierCurve3(a, mid, b);
        const pts = curve.getPoints(SEGMENTS);

        const geo = new THREE.BufferGeometry().setFromPoints(pts);
        const progress = new Float32Array(pts.length);
        for (let k = 0; k < pts.length; k++) progress[k] = k / (pts.length - 1);
        geo.setAttribute('progress', new THREE.BufferAttribute(progress, 1));

        geos.push(geo);
      }
    }
    return geos;
  }, [selected]);

  // Shared shader material
  const material = useMemo(() => {
    const m = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: {
        uTime:        { value: 0 },
        uDuration:    { value: 3000 },
        uActivatedAt: { value: -1 },
        uTheme:       { value: theme },
        uTint:        { value: new THREE.Color(tint as any) },
        uIsHub:       { value: 0.0 },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.NormalBlending,
      toneMapped: false,
    });
    materialRef.current = m;
    return m;
  }, [theme, tint]);

  useEffect(() => {
    const g = groupRef.current;
    if (!g) return;

    // Remove previous line children (dispose only geometries)
    while (g.children.length) {
      const child = g.children.pop()!;
      const line = child as THREE.Line;
      (line.geometry as THREE.BufferGeometry)?.dispose?.();
      child.removeFromParent();
    }

    // Add new lines using the shared material
    geometries.forEach((geo) => {
      const line = new THREE.Line(geo, material);
      g.add(line);
    });

    // Cleanup this batch of geometries when selection changes/unmounts
    return () => {
      geometries.forEach((geo) => geo.dispose());
    };
  }, [geometries, material]);

  useFrame(({ clock }) => {
    const m = materialRef.current;
    if (m) {
      m.uniforms.uTime.value = clock.elapsedTime * 1000.0;
    }
  });

  return <group ref={groupRef} />;
}
