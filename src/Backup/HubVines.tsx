// src/components/HubVines.tsx
'use client';

import * as THREE from 'three';
import { useMemo } from 'react';
import { useFrame } from '@react-three/fiber';

type Node = {
  position: [number, number, number];
  isHub?: boolean;
};

type VineSpec = {
  id: number;
  top: THREE.Vector3;
  bottom: THREE.Vector3;
  length: number;
  path: THREE.Curve<THREE.Vector3>;
};

function colorHex(x: THREE.Color | string | number): THREE.Color {
  return x instanceof THREE.Color ? x : new THREE.Color(x as any);
}

function makeVineCurve(top: THREE.Vector3, bottom: THREE.Vector3, centerBias = 0.15): THREE.QuadraticBezierCurve3 {
  const mid = top.clone().lerp(bottom, 0.5);
  const towardCenter = mid.clone().multiplyScalar(-centerBias);
  const len = top.distanceTo(bottom);
  const control = mid.clone()
    .add(towardCenter)
    .add(new THREE.Vector3(0, Math.max(10, len * 0.08), 0));
  return new THREE.QuadraticBezierCurve3(top, control, bottom);
}

function buildColoredTube(
  path: THREE.Curve<THREE.Vector3>,
  radius: number,
  radialSegments: number,
  tubularSegments: number,
  cBottom: THREE.Color,
  cMid: THREE.Color,
  cTop: THREE.Color
) {
  const curve = new THREE.CatmullRomCurve3(path.getPoints(24));
  const geo = new THREE.TubeGeometry(curve, tubularSegments, radius, radialSegments, false);

  // gradient along length (uv.y)
  const uvs = geo.getAttribute('uv') as THREE.BufferAttribute;
  const N = uvs.count;
  const colors = new Float32Array(N * 3);

  for (let i = 0; i < N; i++) {
    const v = uvs.getY(i); // 0 bottom -> 1 top
    const t1 = THREE.MathUtils.smoothstep(v, 0.0, 0.5);
    const t2 = THREE.MathUtils.smoothstep(Math.max(0, v - 0.5) * 2.0, 0.0, 1.0);
    const midCol = cBottom.clone().lerp(cMid, t1);
    const col = midCol.lerp(cTop, t2);
    colors[i*3+0] = col.r; colors[i*3+1] = col.g; colors[i*3+2] = col.b;
  }
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  return geo;
}

export default function HubVines({
  nodes,
  floorY = -220,
  minHeight = 60,
  radius = 6,
  tint = 0x7FD069, // mint
  gold = 0xF4D35E, // warm highlight
  breathing = true,
  radialSegments = 6,
  tubularSegments = 40,
  inwardTaper = 0.85,
  floorClearance = 16, // <<< keep tips above floor
}: {
  nodes: Node[];
  floorY?: number;
  minHeight?: number;
  radius?: number;
  tint?: THREE.Color | string | number;
  gold?: THREE.Color | string | number;
  breathing?: boolean;
  radialSegments?: number;
  tubularSegments?: number;
  inwardTaper?: number;
  floorClearance?: number;
}) {
  const vines: VineSpec[] = useMemo(() => {
    const list: VineSpec[] = [];
    let id = 0;
    for (const n of nodes) {
      if (!n?.isHub) continue;
      const top = new THREE.Vector3(...n.position);
      // trimmed bottom so we don't penetrate the floor:
      const bottom = new THREE.Vector3(top.x * inwardTaper, floorY + floorClearance, top.z * inwardTaper);
      const len = top.distanceTo(bottom);
      if (len < minHeight) continue;
      const path = makeVineCurve(top, bottom, 0.15);
      list.push({ id: id++, top, bottom, length: len, path });
    }
    return list;
  }, [nodes, floorY, minHeight, inwardTaper, floorClearance]);

  const mint = useMemo(() => colorHex(tint), [tint]);
  const goldCol = useMemo(() => colorHex(gold), [gold]);

  const bodyMaterial = useMemo(() => new THREE.MeshStandardMaterial({
    vertexColors: true,
    emissive: new THREE.Color(0x274131),
    emissiveIntensity: 0.27,
    roughness: 0.5, metalness: 0.2, toneMapped: false,
  }), []);

  const glowMaterial = useMemo(() => new THREE.MeshBasicMaterial({
    color: goldCol, transparent: true, opacity: 0.14,
    blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false,
  }), [goldCol]);

  const capMaterial = useMemo(() => new THREE.MeshBasicMaterial({
    color: goldCol, transparent: true, opacity: 0.22,
    blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false,
  }), [goldCol]);

  const bodies = useMemo(() => vines.map(v => {
    const forest = new THREE.Color(0x396041);
    const geo = buildColoredTube(v.path, radius, radialSegments, tubularSegments, forest, mint, goldCol);
    return { id: v.id, geo, bottom: v.bottom.clone() };
  }), [vines, radius, radialSegments, tubularSegments, mint, goldCol]);

  const glows = useMemo(() => vines.map(v => {
    const curve = new THREE.CatmullRomCurve3(v.path.getPoints(24));
    const geo = new THREE.TubeGeometry(curve, tubularSegments, radius * 1.35, radialSegments, false);
    return { id: v.id, geo };
  }), [vines, radius, radialSegments, tubularSegments]);

  // root caps (small soft spheres at tips)
  const caps = useMemo(() => vines.map(v => {
    const geo = new THREE.SphereGeometry(radius * 1.25, 12, 12);
    return { id: v.id, geo, pos: v.bottom.clone() };
  }), [vines, radius]);

  useFrame(({ clock, scene }) => {
    if (!breathing) return;
    const t = clock.getElapsedTime();
    const scaleY = 1 + Math.sin(t * 0.35) * 0.03;

    scene.traverse((obj) => {
      if (!(obj as THREE.Mesh).isMesh) return;
      const mesh = obj as THREE.Mesh;
      if (mesh.material === bodyMaterial) {
        mesh.scale.y = scaleY;
        const m = mesh.material as THREE.MeshStandardMaterial;
        m.emissiveIntensity = 0.24 + Math.sin(t * 0.45 + mesh.id * 0.07) * 0.07;
      } else if (mesh.material === glowMaterial) {
        mesh.scale.y = 1 + Math.sin(t * 0.35) * 0.028;
        const m = mesh.material as THREE.MeshBasicMaterial;
        m.opacity = THREE.MathUtils.clamp(0.10 + Math.sin(t * 0.48 + mesh.id * 0.11) * 0.07, 0.06, 0.24);
      } else if (mesh.material === capMaterial) {
        const m = mesh.material as THREE.MeshBasicMaterial;
        m.opacity = THREE.MathUtils.clamp(0.14 + Math.sin(t * 0.6 + mesh.id * 0.21) * 0.08, 0.08, 0.28);
      }
    });
  });

  return (
    <>
      <group>
        {bodies.map(({ id, geo }) => <mesh key={`vine-b-${id}`} geometry={geo} material={bodyMaterial} />)}
      </group>
      <group renderOrder={-1}>
        {glows.map(({ id, geo }) => <mesh key={`vine-g-${id}`} geometry={geo} material={glowMaterial} />)}
      </group>
      <group renderOrder={-2}>
        {caps.map(({ id, geo, pos }) => (
          <mesh key={`vine-cap-${id}`} geometry={geo} material={capMaterial} position={pos.toArray()} />
        ))}
      </group>
    </>
  );
}
