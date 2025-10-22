'use client';

import * as THREE from 'three';
import React, { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { PulseConnection } from '@/lib/graphUtils';

type NodeRef = { position: [number, number, number] };

type Props = {
  connections: PulseConnection[];
  nodesRef: NodeRef[];
  beadsPerEdge?: number;
  size?: number;          // px
  brightness?: number;    // 0..inf
  additive?: boolean;
};

function mod1(x: number) {
  return x - Math.floor(x);
}

function bezierPoint(
  a: THREE.Vector3,
  b: THREE.Vector3,
  up: number,
  bias: THREE.Vector3,
  t: number,
  out: THREE.Vector3
) {
  const mid = new THREE.Vector3().addVectors(a, b).multiplyScalar(0.5);
  mid.y += up;
  mid.add(bias);
  const ab = new THREE.Vector3().lerpVectors(a, mid, t);
  const bc = new THREE.Vector3().lerpVectors(mid, b, t);
  return out.copy(ab).lerp(bc, t);
}

export default function PacketBeads({
  connections,
  nodesRef,
  beadsPerEdge = 3,
  size = 6,
  brightness = 1.0,
  additive = true,
}: Props) {
  const pointsRef = useRef<THREE.Points | null>(null);
  const matRef = useRef<THREE.ShaderMaterial | null>(null);
  const { gl } = useThree();

  // Precompute bead “jobs” (which edge, which phase)
  const jobs = useMemo(() => {
    type Job = {
      aIdx: number;
      bIdx: number;
      phase: number; // 0..1 phase offset along edge
      speed: number; // param speed (per second)
    };
    const list: Job[] = [];
    for (const c of connections) {
      const aOk = !!nodesRef[c.a];
      const bOk = !!nodesRef[c.b];
      if (!aOk || !bOk) continue;
      for (let k = 0; k < beadsPerEdge; k++) {
        const phase = (k + 1) / (beadsPerEdge + 1); // staggered along the edge
        const speed = 0.07 + (k % 3) * 0.02;        // slightly different tempos
        list.push({ aIdx: c.a, bIdx: c.b, phase, speed });
      }
    }
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connections, nodesRef, beadsPerEdge]);

  // Geometry with positions for all beads
  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const pos = new Float32Array(jobs.length * 3);
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    g.computeBoundingSphere();
    return g;
  }, [jobs.length]);

  const material = useMemo(() => {
    const m = new THREE.ShaderMaterial({
      vertexShader: `
        precision mediump float;
        uniform float uPixelRatio;
        uniform float uSize;
        void main(){
          vec4 mv = modelViewMatrix * vec4(position,1.0);
          gl_Position = projectionMatrix * mv;
          float dist = -mv.z;
          float s = uSize * clamp(1.0 + dist * 0.0006, 0.8, 3.0);
          gl_PointSize = s * uPixelRatio;
        }
      `,
      fragmentShader: `
        precision mediump float;
        uniform float uBrightness;
        void main(){
          vec2 p = gl_PointCoord * 2.0 - 1.0;
          float r2 = dot(p,p);
          float core = exp(-8.0 * r2);
          float halo = exp(-3.0 * r2) * 0.4;
          float a = clamp(core + halo, 0.0, 1.0);

          vec3 mint = vec3(0.60, 0.90, 0.75);
          vec3 gold = vec3(0.96, 0.83, 0.37);
          vec3 col = mix(mint, gold, core) * uBrightness;

          gl_FragColor = vec4(col, a);
          if (gl_FragColor.a < 0.04) discard;
        }
      `,
      uniforms: {
        uPixelRatio: { value: 1 },
        uSize:       { value: size },
        uBrightness: { value: brightness },
      },
      transparent: true,
      depthWrite: false,
      blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
      toneMapped: false,
    });
    matRef.current = m;
    return m;
  }, [size, brightness, additive]);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    if (!pointsRef.current) return;

    // DPR
    if (matRef.current) {
      matRef.current.uniforms.uPixelRatio.value = Math.min(2, gl.getPixelRatio?.() ?? 1);
    }

    // Update bead positions
    const posAttr = pointsRef.current.geometry.getAttribute('position') as THREE.BufferAttribute;
    const arr = posAttr.array as Float32Array;

    const aVec = new THREE.Vector3();
    const bVec = new THREE.Vector3();
    const out  = new THREE.Vector3();

    let i3 = 0;
    for (let i = 0; i < jobs.length; i++) {
      const j = jobs[i];
      const na = nodesRef[j.aIdx];
      const nb = nodesRef[j.bIdx];
      if (!na || !nb) { arr[i3++] = 0; arr[i3++] = 0; arr[i3++] = 0; continue; }

      aVec.set(...na.position);
      bVec.set(...nb.position);

      const span = aVec.distanceTo(bVec);
      const up = 0.05 * span;
      const mid = aVec.clone().add(bVec).multiplyScalar(0.5);
      const bias = mid.clone().multiplyScalar(-0.06);

      const tt = mod1(t * j.speed + j.phase);
      bezierPoint(aVec, bVec, up, bias, tt, out);

      arr[i3++] = out.x;
      arr[i3++] = out.y;
      arr[i3++] = out.z;
    }
    posAttr.needsUpdate = true;
  });

  return <points ref={pointsRef} geometry={geometry} material={material} />;
}
