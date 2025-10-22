// src/components/MyceliumFloor.tsx
'use client';

import * as THREE from 'three';
import React, { useMemo } from 'react';
import { useFrame } from '@react-three/fiber';

export default function MyceliumFloor({
  size = 9000,
  y = -120,
  seeds = [
    new THREE.Vector2(-1200, 300),
    new THREE.Vector2(800, -500),
    new THREE.Vector2(150, 200),
  ],
}: {
  size?: number;
  y?: number;
  seeds?: THREE.Vector2[];
}) {
  const geo = useMemo(() => new THREE.PlaneGeometry(size, size, 1, 1), [size]);

  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    uniforms: {
      uTime: { value: 0 },
      uSeeds: { value: seeds },
      uSeedCount: { value: seeds.length },
      uScale: { value: 1.0 / size },
    },
    vertexShader: `
      varying vec2 vUvW;
      uniform float uScale;
      void main(){
        vec4 wpos = modelMatrix * vec4(position,1.0);
        vUvW = wpos.xz * uScale;
        gl_Position = projectionMatrix * viewMatrix * wpos;
      }
    `,
    fragmentShader: `
      precision mediump float;
      varying vec2 vUvW;
      uniform float uTime;
      uniform vec2 uSeeds[16]; // up to 16 seeds
      uniform int uSeedCount;

      // Root lines: sum of a few radial “veins” (distance-field ripples)
      float vein(vec2 p, vec2 a){
        float d = length(p-a);
        // main pulse
        float w = 0.006; // line width
        float band = smoothstep(0.02, 0.0, abs(sin(d*30.0) * 0.02));
        // travelling glow outward
        float wave = smoothstep(0.045, 0.0, abs(d - (uTime*0.08)));
        return max(band*0.6, wave*0.4);
      }

      vec3 palette(float t){
        vec3 warm = vec3(0.98, 0.88, 0.62);
        vec3 mint = vec3(0.60, 0.90, 0.75);
        return mix(mint, warm, t);
      }

      void main(){
        vec2 p = vUvW * 10.0; // scale up
        float v = 0.0;
        for(int i=0;i<16;i++){
          if(i>=uSeedCount) break;
          v += vein(p, uSeeds[i]*0.01);
        }
        // base ground tint
        vec3 base = vec3(0.95, 0.94, 0.90); // warm mist-beige, separates from sky
        // biolum color response
        vec3 glow = palette(smoothstep(0.0, 1.0, v));
        float alpha = clamp(v * 0.65, 0.0, 0.9); // slightly stronger presence
        vec3 col = mix(base, glow, alpha);
        gl_FragColor = vec4(col, alpha);
      }
    `,
    blending: THREE.NormalBlending,
    toneMapped: false,
  }), [size, seeds]);

  useFrame(({ clock }) => {
    (mat.uniforms.uTime as any).value = clock.getElapsedTime();
  });

  return (
    <group position={[0, y, 0]} rotation={[-Math.PI/2, 0, 0]}>
      <mesh geometry={geo} material={mat} />
    </group>
  );
}
