// src/components/Fireflies.tsx
'use client';

import * as THREE from 'three';
import { useMemo, useRef, useEffect } from 'react';
import { useFrame, useThree } from '@react-three/fiber';

type Props = {
  /** Number of fireflies */
  count?: number;
  /** Scatter radius on XZ */
  areaRadius?: number;
  /** Vertical span */
  height?: number;
  /** Center Y */
  centerY?: number;
  /** Base point size in px (scaled with distance & DPR) */
  size?: number;
  /** Overall intensity (1.0 default). See also onLightBackground compensation. */
  brightness?: number;
  /** If true, auto-dims/smooths for bright/light backgrounds (recommended for Eco-Flow scene) */
  onLightBackground?: boolean;
  /** Use additive only if you really want punchy glow on dark scenes */
  additive?: boolean;
  /** Optional seed for deterministic layout */
  seed?: number;
};

export default function Fireflies({
  count = 220,
  areaRadius = 4200,
  height = 700,
  centerY = 20,
  size = 7.0,
  brightness = 1.0,
  onLightBackground = true,
  additive = false,
  seed = 12345,
}: Props) {
  const { gl } = useThree();
  const matRef = useRef<THREE.ShaderMaterial | null>(null);
  const pointsRef = useRef<THREE.Points | null>(null);

  // Tiny deterministic PRNG so scatter is stable between renders
  const rand = (() => {
    let s = seed >>> 0;
    return () => {
      // xorshift32
      s ^= s << 13; s >>>= 0;
      s ^= s >> 17; s >>>= 0;
      s ^= s << 5;  s >>>= 0;
      return (s >>> 0) / 4294967296;
    };
  })();

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();

    // positions aren't used (we use aOffset in shader), but Points expects it
    const pos = new Float32Array(count * 3);
    g.setAttribute('position', new THREE.BufferAttribute(pos, 3));

    const aOffset = new Float32Array(count * 3);
    const aSeed   = new Float32Array(count);
    const aHue    = new Float32Array(count);
    const aTier   = new Float32Array(count); // for slightly different motion tempos

    for (let i = 0; i < count; i++) {
      const a = rand() * Math.PI * 2;
      const r = Math.sqrt(rand()) * areaRadius; // blue-noise-ish radial density
      const x = Math.cos(a) * r;
      const z = Math.sin(a) * r;
      const y = centerY + (rand() - 0.5) * height;

      aOffset[i*3+0] = x;
      aOffset[i*3+1] = y;
      aOffset[i*3+2] = z;

      aSeed[i] = rand();
      // hue in [0.38..0.62] → teal to mint range
      aHue[i]  = 0.38 + rand() * 0.24;
      // tier ∈ {0,1,2} for subtle tempo variation
      aTier[i] = Math.floor(rand() * 3);
    }

    g.setAttribute('aOffset', new THREE.BufferAttribute(aOffset, 3));
    g.setAttribute('aSeed',   new THREE.BufferAttribute(aSeed, 1));
    g.setAttribute('aHue',    new THREE.BufferAttribute(aHue, 1));
    g.setAttribute('aTier',   new THREE.BufferAttribute(aTier, 1));
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, centerY, 0), areaRadius + height);
    return g;
  }, [count, areaRadius, height, centerY, seed]);

  const material = useMemo(() => {
    // Scene compensation: soften halos & clamp intensity for light backgrounds
    const alphaCap   = onLightBackground ? 0.65 : 0.9;
    const brightnessScale = onLightBackground ? 0.75 : 1.0;

    const m = new THREE.ShaderMaterial({
      vertexShader: `
        precision mediump float;
        attribute vec3 aOffset;
        attribute float aSeed;
        attribute float aHue;
        attribute float aTier;

        uniform float uTime;
        uniform float uSize;
        uniform float uPixelRatio;

        varying float vHue;
        varying float vTwinkle;
        varying float vAlphaBias;

        // layered, bounded "organic" drift (no huge excursions)
        vec3 drift(vec3 p, float s, float t){
          float t1 = t*0.12 + s*6.28318;
          float t2 = t*0.07 + s*12.47;
          float t3 = t*0.095 + s*3.31;

          vec3 d1 = vec3(
            sin(t1*0.9)*0.7 + cos(t2*0.5)*0.3,
            sin(t2*0.8)*0.6 + sin(t3*0.6)*0.4,
            cos(t1*0.7)*0.6 + sin(t3*0.7)*0.4
          );

          vec3 d2 = vec3(
            sin(t1*1.7 + 1.1)*0.35,
            cos(t2*1.3 + 0.7)*0.35,
            sin(t3*1.5 + 2.0)*0.35
          );

          // tier offsets → subtle variety in tempo/phase
          float k = 18.0 + aTier * 6.0;
          return p + (d1 * 26.0 + d2 * 12.0);
        }

        void main(){
          float t = uTime;
          vec3 pos = drift(aOffset, aSeed, t);

          // gentle vertical bob
          pos.y += sin(t*0.23 + aSeed*20.0) * 8.0;

          vec4 mv = modelViewMatrix * vec4(pos, 1.0);
          gl_Position = projectionMatrix * mv;

          float dist = -mv.z;
          // distance-based size; bounded so points don’t explode
          float sizePx = uSize * clamp(1.0 + dist * 0.0006, 0.8, 3.0);
          gl_PointSize = sizePx * uPixelRatio;

          vHue = aHue;

          // twinkle with tiered tempo & seed phase
          float tw1 = sin(t*0.9  + aSeed*50.0 + aTier*0.6)*0.5 + 0.5;
          float tw2 = sin(t*1.37 + aSeed*73.0 + aTier*1.1)*0.5 + 0.5;
          vTwinkle = mix(tw1, tw2, 0.35);

          // slight alpha bias by distance (helps avoid harsh pops on light bg)
          vAlphaBias = clamp(0.85 - dist * 0.00012, 0.55, 0.95);
        }`,
      fragmentShader: `
        precision mediump float;
        varying float vHue;
        varying float vTwinkle;
        varying float vAlphaBias;

        uniform float uBrightness;
        uniform float uAlphaCap; // scene compensation

        // teal→mint ramp
        vec3 ramp(float t){
          vec3 teal  = vec3(0.25, 0.75, 0.65);
          vec3 mint  = vec3(0.60, 0.90, 0.75);
          return mix(teal, mint, smoothstep(0.0,1.0,t));
        }

        void main(){
          vec2 uv = gl_PointCoord * 2.0 - 1.0;
          float r2 = dot(uv, uv);

          // biolum core + soft halo; capped for light scenes
          float core  = exp(-6.0 * r2);
          float halo  = exp(-2.0 * r2) * 0.42;
          float a = clamp((core + halo) * vAlphaBias, 0.0, uAlphaCap);

          // twinkle modulates both color lift and subtle alpha
          float tw = mix(0.8, 1.2, vTwinkle);
          vec3 col = ramp(vHue) * tw * uBrightness;

          gl_FragColor = vec4(col, a);
          if (gl_FragColor.a < 0.025) discard;
        }`,
      uniforms: {
        uTime:       { value: 0 },
        uSize:       { value: size },
        uPixelRatio: { value: 1 },
        uBrightness: { value: brightness * brightnessScale },
        uAlphaCap:   { value: alphaCap },
      },
      transparent: true,
      depthWrite: false,
      blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
      toneMapped: false,
    });
    matRef.current = m;
    return m;
  }, [size, brightness, onLightBackground, additive]);

  useEffect(() => {
    if (matRef.current) {
      matRef.current.uniforms.uPixelRatio.value = Math.min(2, gl.getPixelRatio?.() ?? 1);
    }
    if (pointsRef.current) pointsRef.current.frustumCulled = false;

    return () => {
      // Cleanup on unmount
      pointsRef.current?.geometry?.dispose?.();
      (pointsRef.current?.material as THREE.Material | undefined)?.dispose?.();
    };
  }, [gl]);

  useFrame(({ clock }) => {
    if (matRef.current) {
      matRef.current.uniforms.uTime.value = clock.getElapsedTime();
    }
  });

  return <points ref={pointsRef} geometry={geometry} material={material} />;
}
