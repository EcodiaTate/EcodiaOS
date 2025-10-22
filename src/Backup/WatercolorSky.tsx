// src/components/WatercolorSky.tsx
'use client';

import * as THREE from 'three';
import React, { useMemo } from 'react';
import { useFrame } from '@react-three/fiber';

export default function WatercolorSky({
  radius = 8000,
  speed = 0.006,
}: { radius?: number; speed?: number }) {
  // Inverted sphere with a soft gradient; we modulate with a slow time term
  const geo = useMemo(() => new THREE.SphereGeometry(radius, 48, 32), [radius]);
  const mat = useMemo(() => new THREE.ShaderMaterial({
    side: THREE.BackSide,
    transparent: false,
    depthWrite: false,
    uniforms: {
      uTime: { value: 0 },
    },
    vertexShader: `
      varying vec3 vWorld;
      void main(){
        vec4 wpos = modelMatrix * vec4(position,1.0);
        vWorld = wpos.xyz;
        gl_Position = projectionMatrix * viewMatrix * wpos;
      }
    `,
    fragmentShader: `
      precision mediump float;
      varying vec3 vWorld;
      uniform float uTime;

      // Mist → Gold (low sat) → Mint
      vec3 grad(float t){
        vec3 mist = vec3(0.92, 0.96, 0.94);
        vec3 gold = vec3(0.96, 0.83, 0.37);
        vec3 mint = vec3(0.50, 0.82, 0.58);
        vec3 a = mix(mist, gold, smoothstep(0.0, 0.45, t));
        return mix(a, mint, smoothstep(0.40, 1.0, t));
      }

      float noise(vec3 p){
        // super cheap hash-noise
        p = fract(p*0.3183099 + 0.1);
        p *= 17.0;
        return fract(p.x*p.y*p.z*(p.x+p.y+p.z));
      }

      void main(){
        vec3 n = normalize(vWorld);
        float t = n.y*0.5+0.5;               // up→down gradient
        float drift = sin(uTime*0.04 + n.x*1.3 + n.z*1.1)*0.03;
        float misty = clamp(t + drift, 0.0, 1.0);

        // faint “spirit clouds”: low-contrast cards via noise
        float clouds = smoothstep(0.85, 1.0, noise(n*2.2 + uTime*0.01));
        vec3 col = grad(misty);
        col = mix(col, col + vec3(0.08,0.09,0.10), clouds*0.08);

        gl_FragColor = vec4(col, 1.0);
      }
    `,
    toneMapped: false,
  }), []);

  useFrame(({ clock }) => {
    (mat.uniforms.uTime as any).value = clock.getElapsedTime();
  });

  return <mesh geometry={geo} material={mat} />;
}
