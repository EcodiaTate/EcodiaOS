// src/components/CausticDrift.tsx
'use client';

import * as THREE from 'three';
import React, { useMemo } from 'react';
import { useFrame } from '@react-three/fiber';

export default function CausticDrift({
  intensity = 0.12,
  scale = 0.002,
}: { intensity?: number; scale?: number }) {
  // Fullscreen quad in NDC that writes an additive overlay via custom blend
  const geo = useMemo(() => new THREE.PlaneGeometry(2, 2), []);
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    uniforms: {
      uTime: { value: 0 },
      uIntensity: { value: intensity },
      uScale: { value: scale },
    },
    vertexShader: `
      void main(){ gl_Position = vec4(position,1.0); }
    `,
    fragmentShader: `
      precision mediump float;
      uniform float uTime;
      uniform float uIntensity;
      uniform float uScale;

      float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1,311.7)))*43758.5453123); }
      float noise(vec2 p){
        vec2 i=floor(p); vec2 f=fract(p);
        float a=hash(i), b=hash(i+vec2(1,0));
        float c=hash(i+vec2(0,1)), d=hash(i+vec2(1,1));
        vec2 u=f*f*(3.0-2.0*f);
        return mix(a,b,u.x)+ (c-a)*u.y*(1.0-u.x)+ (d-b)*u.x*u.y;
      }

      void main(){
        vec2 uv = gl_FragCoord.xy * uScale;
        float t = uTime*0.05;
        float n = 0.0;
        n += noise(uv + vec2(t,0.0))*0.6;
        n += noise(uv*1.7 + vec2(0.0,-t*0.7))*0.4;
        n = smoothstep(0.4, 0.95, n);
        vec3 gold = vec3(0.96, 0.83, 0.37);
        vec2 p = (gl_FragCoord.xy / 2048.0) * 2.0 - 1.0; // normalize-ish; adjust screen scale as needed
        float radial = smoothstep(1.0, 0.2, length(p)); // less at center, more at edges
        gl_FragColor = vec4(gold * n * uIntensity * radial, n * uIntensity * radial);
      }
    `,
    toneMapped: false,
  }), [intensity, scale]);

  useFrame(({ clock }) => {
    (mat.uniforms.uTime as any).value = clock.getElapsedTime();
  });

  return <mesh geometry={geo} material={mat} />;
}
