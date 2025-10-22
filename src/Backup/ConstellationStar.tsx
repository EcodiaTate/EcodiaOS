// src/components/ConstellationStar.tsx
'use client';

import * as THREE from 'three';
import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';

interface Star {
  id: string;
  position: [number, number, number];
  word: string;
  size: number; // world units (e.g., 50–80)
  glow: number; // 0..1 (not strictly required; used as emphasis)
}

interface Props {
  star: Star;
  isSelected: boolean;
  onClick: () => void;
  /** 0..1 theme darkness (affects base emissive/opacity), default 0.35 */
  theme?: number;
  /** Optional tint to bias the star color toward eco palette */
  tint?: THREE.Color | string | number;
}

/** Deterministic 0..1 hash from a string (stable per-star twinkle phase) */
function hash01(key: string) {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  h += h << 13; h ^= h >>> 7; h += h << 3; h ^= h >>> 17; h += h << 5;
  return (h >>> 0) / 4294967295;
}

export default function ConstellationStar({
  star,
  isSelected,
  onClick,
  theme = 0.35,
  tint = 0xdaf3e6, // pale eco mint
}: Props) {
  const coreRef = useRef<THREE.Mesh | null>(null);
  const auraRef = useRef<THREE.Mesh | null>(null);
  const matRef  = useRef<THREE.MeshPhysicalMaterial | null>(null);

  // Safe reduced-motion check for SSR
  const reduceMotion = useMemo(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return false;
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }, []);

  const phase = useMemo(() => hash01(star.id) * Math.PI * 2, [star.id]);

  // Sizes / scales
  const baseRadius = star.size;
  const selectedScale = 1.45;
  const auraScaleBase = 1.35;
  const auraScaleSelected = 1.75;

  // Colors (eco-solarpunk, light scene)
  const bodyColor = useMemo(() => new THREE.Color('#EAF6EF'), []);     // misty mint white
  const tintColor = useMemo(() => new THREE.Color(tint as any), [tint]);
  const goldGlow  = useMemo(() => new THREE.Color('#F4D35E'), []);     // warm highlight
  const mintGlow  = useMemo(() => new THREE.Color('#CFE9D6'), []);     // subtle mint
  const emissiveBase = isSelected ? goldGlow : mintGlow;

  // Geometry + materials are stable
  const coreGeom = useMemo(
    () => new THREE.SphereGeometry(baseRadius * (isSelected ? selectedScale : 1), 24, 24),
    // re-create if selection changes (size is different)
    [baseRadius, isSelected]
  );
  const auraGeom = useMemo(
    () => new THREE.SphereGeometry(baseRadius, 24, 24),
    [baseRadius]
  );

  const coreMat = useMemo(() => {
    const m = new THREE.MeshPhysicalMaterial({
      color: bodyColor.clone().lerp(tintColor, 0.2), // slight eco tint
      emissive: emissiveBase,
      emissiveIntensity: isSelected ? 2.2 : 1.2,
      roughness: 0.25,
      metalness: 0.35,
      clearcoat: 0.6,
      clearcoatRoughness: 0.25,
      sheen: 0.6,
      sheenColor: tintColor,
      toneMapped: false,
    });
    matRef.current = m;
    return m;
  }, [bodyColor, tintColor, emissiveBase, isSelected]);

  const auraMat = useMemo(
    () =>
      new THREE.MeshBasicMaterial({
        color: isSelected ? goldGlow : mintGlow,
        transparent: true,
        opacity: isSelected ? 0.22 : 0.12,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
        toneMapped: false,
      }),
    [isSelected, goldGlow, mintGlow]
  );

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const speed = reduceMotion ? 0 : 1.4;
    const amp = isSelected ? 0.12 : 0.06;

    // gentle size twinkle
    const s = speed === 0 ? 1 : 1 + Math.sin(t * speed + phase) * amp;

    // emissive breathing (slightly stronger when selected)
    const baseEmissive = isSelected ? (1.8 + theme * 0.6) : (1.1 + theme * 0.4);
    const emissivePulse =
      speed === 0
        ? baseEmissive
        : baseEmissive + Math.sin(t * (speed * 0.9) + phase) * 0.22;

    if (coreRef.current) {
      coreRef.current.scale.set(s, s, s);
    }
    if (matRef.current) {
      matRef.current.emissiveIntensity = emissivePulse;
    }
    if (auraRef.current) {
      const aScale = (isSelected ? auraScaleSelected : auraScaleBase) * s;
      auraRef.current.scale.set(aScale, aScale, aScale);
      const m = auraMat;
      // breathe aura opacity within a tasteful range; bias by theme
      const target = (isSelected ? 0.22 : 0.12) * (0.9 + theme * 0.3);
      const osc =
        speed === 0
          ? 0
          : Math.sin(t * (speed * 0.8) + phase) * 0.04;
      (m as THREE.MeshBasicMaterial).opacity = THREE.MathUtils.clamp(
        target + osc,
        0.06,
        0.28
      );
    }
  });

  return (
    <group
      position={star.position}
      onPointerDown={(e) => {
        e.stopPropagation();
        onClick();
      }}
      onPointerOver={() => { if (typeof document !== 'undefined') document.body.style.cursor = 'pointer'; }}
      onPointerOut={() =>  { if (typeof document !== 'undefined') document.body.style.cursor = 'auto'; }}
    >
      {/* Core star */}
      <mesh ref={coreRef} geometry={coreGeom} material={coreMat} />

      {/* Soft additive aura halo */}
      <mesh ref={auraRef} geometry={auraGeom} material={auraMat} renderOrder={-1} />
    </group>
  );
}
