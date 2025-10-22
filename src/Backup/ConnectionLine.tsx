// src/components/ConnectionLine.tsx
'use client';

import * as THREE from 'three';
import { useMemo, useRef, useEffect } from 'react';
import { useFrame } from '@react-three/fiber';

import vertexShader from '@/shaders/connection.vert';
import fragmentShader from '@/shaders/connection.frag'; // supportive, eco-solarpunk ramp
import { PulseConnection, PULSE_DURATION } from '@/lib/graphUtils';

interface NodeRef {
  position: [number, number, number];
  isOuter?: boolean;
  isStar?: boolean;
  // future: isHub?: boolean
}

interface Props {
  connection: PulseConnection;
  nodesRef: NodeRef[];
  /** 0..1, scene darkness bias -> drives base opacity in shader (default ~0.35–0.4 for light scenes) */
  theme?: number;
  /** Small tint applied to ramp (eco-mint by default) */
  tint?: THREE.Color | string | number;
  /** Spline segment count (higher == smoother) */
  segments?: number;
}

export default function ConnectionLine({
  connection,
  nodesRef,
  theme = 0.38,
  tint = 0xDAF3E6, // Mist/mint bias for light scene
  segments = 10,
}: Props) {
  // Validate indices early
  const aNode = nodesRef[connection.a];
  const bNode = nodesRef[connection.b];
  if (!aNode || !bNode) return null;

  // Maintain “no single god-core” tone: skip star↔star
  if (aNode.isStar && bNode.isStar) return null;

  const shaderRef = useRef<THREE.ShaderMaterial | null>(null);
  const lineRef = useRef<THREE.Line | null>(null);

  // Subtle hub boost for edges that are not outer-ring → not outer-ring
  const isHubEdge =
    (!aNode.isOuter && !bNode.isOuter) ? 1.0 : 0.0;

  const start = useMemo(
    () => new THREE.Vector3(...aNode.position),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [aNode.position[0], aNode.position[1], aNode.position[2]]
  );
  const end = useMemo(
    () => new THREE.Vector3(...bNode.position),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [bNode.position[0], bNode.position[1], bNode.position[2]]
  );

  // Deterministic edge seed (stable shape, no jitter across renders)
  const seed = useMemo(() => {
    // Mix indices into a stable 32-bit-ish int, then into [0,1)
    const x = (connection.a + 1) * 73856093 ^ (connection.b + 1) * 19349663;
    const s = Math.sin(x * 0.000123) * 43758.5453123;
    return s - Math.floor(s);
  }, [connection.a, connection.b]);

  const curve = useMemo(() => {
    // Midpoint
    const mid = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);

    // Upward arch ~5% of span + tiny deterministic variation
    const span = start.distanceTo(end);
    const up = 0.05 * span + (seed - 0.5) * 0.01 * span;
    mid.y += up;

    // Gentle lateral drift (perpendicular to direction), makes it feel like a living stream
    const dir = new THREE.Vector3().subVectors(end, start).normalize();
    // Choose a fallback up if dir ≈ world up
    const worldUp = Math.abs(dir.dot(new THREE.Vector3(0, 1, 0))) > 0.98
      ? new THREE.Vector3(1, 0, 0)
      : new THREE.Vector3(0, 1, 0);
    const perp = new THREE.Vector3().crossVectors(dir, worldUp).normalize();
    const lateral = (seed * 2.0 - 1.0) * 0.025 * span; // ±2.5% of span
    mid.addScaledVector(perp, lateral);

    return new THREE.QuadraticBezierCurve3(start, mid, end);
  }, [start, end, seed]);

  const points = useMemo(() => curve.getPoints(Math.max(3, segments)), [curve, segments]);

  // Geometry with a 'progress' attribute (0..1 along the curve)
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry().setFromPoints(points);
    const progress = new Float32Array(points.length);
    for (let i = 0; i < points.length; i++) progress[i] = i / (points.length - 1);
    geo.setAttribute('progress', new THREE.BufferAttribute(progress, 1));
    geo.computeBoundingSphere();
    return geo;
  }, [points]);

  // Material w/ supportive blending for light scene, depthWrite off for soft layering
  const material = useMemo(() => {
    const tintColor = new THREE.Color(tint as any);
    const mat = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms: {
        uTime:        { value: 0 },
        uDuration:    { value: PULSE_DURATION },
        uActivatedAt: { value: -1 },
        uTheme:       { value: theme },        // 0..1
        uTint:        { value: tintColor },    // vec3
        uIsHub:       { value: isHubEdge },    // 0..1
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.NormalBlending, // physical presence on light background
      toneMapped: false,
    });
    return mat;
  }, [theme, tint, isHubEdge]);

  // Attach & keep refs in sync, clean up previous instances
  useEffect(() => {
    shaderRef.current = material;

    if (!lineRef.current) {
      lineRef.current = new THREE.Line(geometry, material);
      lineRef.current.frustumCulled = false; // avoid thin-line cull pops
    } else {
      // Dispose old geo/mat before swapping to prevent leaks
      const oldGeo = lineRef.current.geometry as THREE.BufferGeometry | undefined;
      const oldMat = lineRef.current.material as THREE.Material | undefined;
      lineRef.current.geometry = geometry;
      lineRef.current.material = material;
      if (oldGeo && oldGeo !== geometry) oldGeo.dispose();
      if (oldMat && oldMat !== material) oldMat.dispose();
    }

    return () => {
      // Cleanup when this component unmounts or dependencies change
      if (lineRef.current) {
        lineRef.current.geometry?.dispose?.();
        (lineRef.current.material as THREE.Material | undefined)?.dispose?.();
      }
    };
  }, [geometry, material]);

  // Drive time + activation
  useFrame(({ clock }) => {
    const nowMs = clock.getElapsedTime() * 1000;
    const s = shaderRef.current;
    if (!s) return;
    s.uniforms.uTime.value = nowMs;
    s.uniforms.uActivatedAt.value = connection.activatedAt ?? -1;
  });

  return lineRef.current ? <primitive object={lineRef.current} /> : null;
}
