'use client';

import * as THREE from 'three';
import React, { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';

type Props = {
  count?: number;
  radius?: number;
  height?: number; // vertical travel span
  baseY?: number;
  opacity?: number;
  width?: number;  // plane width in world units
  length?: number; // plane height in world units
};

export default function Wisps({
  count = 16,
  radius = 3200,
  height = 900,
  baseY = -40,
  opacity = 0.22,
  width = 24,
  length = 180,
}: Props) {
  const meshRef = useRef<THREE.InstancedMesh | null>(null);
  const matRef  = useRef<THREE.ShaderMaterial | null>(null);
  const { camera } = useThree();

  // Seeds + base offsets (stable)
  const seeds = useMemo(() => Float32Array.from({ length: count }, () => Math.random()), [count]);
  const offsets = useMemo(() => {
    const a = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      const ang = Math.random() * Math.PI * 2;
      const r = Math.sqrt(Math.random()) * radius;
      a[i*3+0] = Math.cos(ang) * r;
      a[i*3+1] = baseY + Math.random() * height * 0.3;
      a[i*3+2] = Math.sin(ang) * r;
    }
    return a;
  }, [count, radius, baseY, height]);

  // Shared geometry (simple plane)
  const geometry = useMemo(() => new THREE.PlaneGeometry(width, length, 1, 1), [width, length]);

  // Shader material (soft minty plume)
  const material = useMemo(() => {
    const m = new THREE.ShaderMaterial({
      vertexShader: `
        varying vec2 vUv;
        void main(){
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0);
        }`,
      fragmentShader: `
        precision mediump float;
        varying vec2 vUv;
        uniform float uOpacity;

        void main(){
          // radial-ish softness (ellipse)
          vec2 uv = vUv * 2.0 - 1.0;
          uv.x *= 0.6;                 // thinner sideways
          float r2 = dot(uv, uv);
          float a = exp(-r2 * 2.5) * 0.8 + exp(-r2 * 6.0) * 0.25;
          vec3 col = vec3(0.52, 0.86, 0.72); // mint
          gl_FragColor = vec4(col, a * uOpacity);
          if (gl_FragColor.a < 0.02) discard;
        }`,
      uniforms: {
        uOpacity: { value: opacity },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      toneMapped: false,
      side: THREE.DoubleSide,
    });
    matRef.current = m;
    return m;
  }, [opacity]);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const mesh = meshRef.current;
    if (!mesh) return;

    const q = new THREE.Quaternion();
    const s = new THREE.Vector3(1,1,1);
    const m = new THREE.Matrix4();
    const camQ = camera.quaternion; // billboard: face camera

    for (let i = 0; i < count; i++) {
      const seed = seeds[i];
      const x0 = offsets[i*3+0];
      const y0 = offsets[i*3+1];
      const z0 = offsets[i*3+2];

      // rise & meander
      const y = y0 + (t * 18.0 + seed * 500.0) % height;
      const x = x0 + Math.sin(t * 0.12 + seed * 40.0) * 28.0;
      const z = z0 + Math.cos(t * 0.09 + seed * 31.0) * 28.0;

      // face camera
      q.copy(camQ);

      // slight scale flutter
      s.set(1, 1 + Math.sin(t * 0.6 + seed * 10.0) * 0.08, 1);

      m.compose(new THREE.Vector3(x, y, z), q, s);
      mesh.setMatrixAt(i, m);
    }
    mesh.instanceMatrix.needsUpdate = true;
  });

  return <instancedMesh ref={meshRef} args={[geometry, material, count]} />;
}
