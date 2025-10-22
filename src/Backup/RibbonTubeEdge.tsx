// src/components/RibbonTubeEdge.tsx
'use client';

import * as THREE from 'three';
import React, { useMemo } from 'react';
import { PulseConnection } from '@/lib/graphUtils';

type NodeRef = { position: [number, number, number] };
export default function RibbonTubeEdge({
  connection, nodesRef, radius=8, glow=1.35,
}: { connection: PulseConnection; nodesRef: NodeRef[]; radius?: number; glow?: number; }) {
  const a = nodesRef[connection.a], b = nodesRef[connection.b];
  if (!a || !b) return null;

  const { bodyGeo, glowGeo, bodyMat, glowMat } = useMemo(() => {
    const A = new THREE.Vector3(...a.position);
    const B = new THREE.Vector3(...b.position);
    const span = A.distanceTo(B);
    const mid = A.clone().add(B).multiplyScalar(0.5);
    const up  = 0.05 * span;
    const bias = mid.clone().multiplyScalar(-0.06);
    const ctrl = mid.clone(); ctrl.y += up; ctrl.add(bias);
    const bez = new THREE.QuadraticBezierCurve3(A, ctrl, B);
    const curve = new THREE.CatmullRomCurve3(bez.getPoints(24));
    const bodyGeo = new THREE.TubeGeometry(curve, 60, radius, 8, false);
    const glowGeo = new THREE.TubeGeometry(curve, 60, radius*glow, 8, false);

    const bodyMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color(0x6fd1a8).lerp(new THREE.Color(0xF4D35E), 0.25),
      emissive: new THREE.Color(0x204235),
      emissiveIntensity: 0.22,
      roughness: 0.5, metalness: 0.2, toneMapped: false,
    });
    const glowMat = new THREE.MeshBasicMaterial({
      color: 0xF4D35E, transparent: true, opacity: 0.12,
      blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false,
    });

    return { bodyGeo, glowGeo, bodyMat, glowMat };
  }, [a, b, radius, glow]);

  return (
    <>
      <mesh geometry={bodyGeo} material={bodyMat} />
      <mesh geometry={glowGeo} material={glowMat} renderOrder={-1} />
    </>
  );
}
