// src/components/EcodiaStarCanvas.tsx
'use client';

import { useRef, useState, useEffect, useMemo } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import * as THREE from 'three';

// Zustand Stores
import { useSoulStore } from '@/stores/useSoulStore';
import { useModeStore } from '@/stores/useModeStore';
import { useNodeStore } from '@/stores/useNodeStore';

// New light-scene components
import WatercolorSky from './WatercolorSky';
import CausticDrift from './CausticDrift';
import MyceliumFloor from './MyceliumFloor';
import HubVines from './HubVines';
import Fireflies from './Fireflies';

// Canvas Components (supportive vibe)
import ExtendLinesClient from './ExtendLinesClient';
import CameraRig from './CameraRig';
import BrainNode from './BrainNode';
import ConstellationStar from './ConstellationStar';
import ConnectionLine from './ConnectionLine';
import ConstellationConnections from './ConstellationConnections';
import FlowController from './FlowController'; // replaces PulseController
import Wisps from './Wisps'; // replaces PulseController
import RibbonTubeEdge from './RibbonTubeEdge'; // replaces PulseController
import PacketBeads from './PacketBeads'; // replaces PulseController

// Data and Utils
import PLACEHOLDER_WORDS from '@/lib/placholderWords';
import {
  generateNodes,
  generateConnections,
  PulseConnection,
  Node as GraphNode,
  Star,
} from '@/lib/graphUtils';

type CanvasNode = GraphNode & { isCore?: boolean; system: string; isHub?: boolean };

function ControlsUpdater() {
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null;
  useFrame(() => controls?.update());
  return null;
}

/** Layered canopy scatter: places nodes across a wide, shallow field */
function applyCanopyLayout(
  nodes: CanvasNode[],
  options?: {
    radius?: number;
    layers?: number;
    layerGap?: number;
    yBase?: number;
    jitterY?: number;
  }
) {
  const R = options?.radius ?? 2200;
  const LAYERS = Math.max(1, Math.floor(options?.layers ?? 4));
  const GAP = options?.layerGap ?? 80;
  const YBASE = options?.yBase ?? -60;
  const JY = options?.jitterY ?? 10;

  // pick a few hubs (~8%) to drive subtle boosts / trunks if needed
  const hubCount = Math.max(1, Math.floor(nodes.length * 0.08));
  const hubIdxs = new Set<number>();
  while (hubIdxs.size < hubCount) hubIdxs.add(Math.floor(Math.random() * nodes.length));

  for (let i = 0; i < nodes.length; i++) {
    const a = Math.random() * Math.PI * 2;
    const r = Math.sqrt(Math.random()) * R; // uniform disc
    const x = r * Math.cos(a);
    const z = r * Math.sin(a);
    const band = Math.floor(Math.random() * LAYERS);
    const y = YBASE + band * GAP + (Math.random() - 0.5) * JY;

    nodes[i].position = [x, y, z];
    nodes[i].isHub = hubIdxs.has(i);
    // no central core
  }
}

export default function EcodiaStarCanvas() {
  const nodesRef = useRef<CanvasNode[]>([]);
  const connectionsRef = useRef<PulseConnection[]>([]);
  const [connections, setConnections] = useState<PulseConnection[]>([]);
  const adjacencyMap = useRef<Record<number, number[]>>({});

  // --- Zustand ---
  const { selectedWords, toggleWordSelection, setMatchedSoul, clearSoul } = useSoulStore();
  const mode = useModeStore((s) => s.mode);
  const setMode = useModeStore((s) => s.setMode);
  const { registerNode, clearNodes } = useNodeStore();

  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [generatedSoul, setGeneratedSoul] = useState<string | null>(null);

  const isAutoRotateEnabled = mode !== 'constellation';
  const isUserControlEnabled = mode === 'constellation';

  const selectedStars = useMemo(() => {
    return nodesRef.current.filter(
      (n) => (n as any).isStar && selectedWords.includes(n.word!)
    ) as Star[];
  }, [selectedWords]);

  // ----- Initial graph creation (with canopy layout) -----
  useEffect(() => {
    clearSoul();

    // Seed stars from placeholder words
    const stars: Star[] = PLACEHOLDER_WORDS.map((word, i) => ({
      id: `star-${i}`,
      position: [0, 0, 0], // will be set by layout
      word,
      size: Math.random() * 30 + 50,
      glow: Math.random() * 10 + 5,
      isStar: true,
    }));

    const nodes = generateNodes(stars) as CanvasNode[];
    applyCanopyLayout(nodes, { radius: 2300, layers: 4, layerGap: 90, yBase: -40, jitterY: 12 });

    const generatedConnections = generateConnections(nodes, adjacencyMap.current);

    nodesRef.current = nodes;
    connectionsRef.current = generatedConnections;
    setConnections(generatedConnections);

    clearNodes();
    stars.forEach((s, i) => registerNode(s.word, new THREE.Vector3(...nodes[i].position)));

    setReady(true);
  }, [clearNodes, clearSoul, registerNode]);

  const handleSelect = (star: Star) => {
    if (mode === 'constellation' && !generatedSoul) toggleWordSelection(star.word, 10);
  };

  const finalizeSoul = async () => {
    if (selectedWords.length !== 10) return;
    setLoading(true);
    setGeneratedSoul(null);

    try {
      const response = await fetch('/api/voxis/generate-soul', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ words: selectedWords }),
      });
      const data = await response.json();
      if (!response.ok || !data.soul) throw new Error(data.error || 'Failed to generate soul');

      const soulId = data.event_id || data.key_id || '';
      sessionStorage.setItem('soulnode_id', soulId);
      sessionStorage.setItem('soulnode_words', JSON.stringify(data.words || selectedWords));
      sessionStorage.setItem('soulnode_plaintext', data.soul);

      setMatchedSoul(soulId, data.words || selectedWords);
      setGeneratedSoul(data.soul);

      setTimeout(() => setMode('hub'), 4000);
    } catch (err: any) {
      console.error('Soul generation failed:', err);
      setGeneratedSoul(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  if (!ready) return null;

  return (
    <>
      <ExtendLinesClient />
      <div className="relative w-full h-screen">
        {/* fonts */}
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@300;400;700&family=Fjalla+One&display=swap"
          rel="stylesheet"
        />

        <Canvas
          camera={{ position: [0, 120, 4200], fov: 60, near: 0.1, far: 15000 }}
          gl={{ logarithmicDepthBuffer: true, antialias: true }}
          onCreated={({ gl, scene }) => {
            gl.toneMapping = THREE.ACESFilmicToneMapping;
            gl.outputColorSpace = THREE.SRGBColorSpace;
            gl.setClearColor('#ecf5f1', 1); // Mist base
            scene.fog = new THREE.FogExp2(new THREE.Color('#e8f5ef'), 0.00014);
          }}
        >
          {/* Light Eywa backdrop */}
          <WatercolorSky />
          <CausticDrift intensity={0.10} scale={0.0022} />

          {/* Floor + Vines */}
          <MyceliumFloor size={9000} y={-220} />
          <HubVines nodes={nodesRef.current} floorY={-220} radius={6} />

          {/* Fireflies tuned for light background */}
          <Fireflies
  count={160}
  areaRadius={4200}
  height={700}
  centerY={40}
  size={6.5}
  brightness={0.95}
  onLightBackground  // <<< important
  additive={false}   // <<< no additive on bright scenes
/>

<Wisps count={10} radius={3400} height={900} baseY={-40} opacity={0.16} width={18} length={160} />

          {/*eeeeeeeeeeeeee Lights (gentle, supportive) */}
          <ambientLight intensity={0.55} />
<directionalLight position={[1200, 1600, 800]} intensity={0.5} />
<directionalLight position={[-800, 1200, -1200]} intensity={0.28} />

          {connections.filter(c => /* your hub↔hub predicate */ false).slice(0, 12).map(c => (
  <RibbonTubeEdge key={`tube-${c.a}-${c.b}`} connection={c} nodesRef={nodesRef.current} radius={8} />
))}

          {/* Camera easing / rig */}
          <CameraRig />

          {/* Distributed flow controller */}
          <FlowController
            nodesRef={nodesRef.current}
            connectionsRef={connectionsRef.current}
            adjacencyMap={adjacencyMap.current}
            baseIntervalMs={900}
            baseSeedsPerBurst={2}
            maxDepth={14}
            maxBranches={2}
          />

          {/* Controls */}
          <OrbitControls
            autoRotate={mode !== 'constellation'}
            autoRotateSpeed={0.15}
            enableDamping
            dampingFactor={0.06}
            rotateSpeed={0.6}
            enablePan={isUserControlEnabled}
            enableZoom={isUserControlEnabled}
            enableRotate
            makeDefault
          />
          <ControlsUpdater />

          {/* Constellation mode overlay */}
          {mode === 'constellation' &&
            nodesRef.current
              .filter((n) => (n as any).isStar)
              .map((n) => (
                <ConstellationStar
                  key={n.id}
                  star={{
                    id: n.id!,
                    position: n.position,
                    word: n.word!,
                    size: n.size!,
                    glow: n.glow!,
                  }}
                  isSelected={selectedWords.includes(n.word!)}
                  onClick={() => handleSelect(n as Star)}
                />
              ))}

          {mode === 'constellation' && <ConstellationConnections selected={selectedStars} />}

          {/* Node anchors */}
          {nodesRef.current.map((node, i) => (
            <BrainNode key={i} node={node} />
          ))}

          {/* Ribbons */}
          {connections.map((connection) => (
            <ConnectionLine
              key={`${connection.a}-${connection.b}`}
              connection={connection}
              nodesRef={nodesRef.current}
              // theme={0.35}
              // tint={0xDAF3E6}
            />
          ))}
          <PacketBeads connections={connections} nodesRef={nodesRef.current} beadsPerEdge={2} size={6} />

        </Canvas>

        {mode === 'constellation' && (
          <div className="ecodia-star-ui pointer-events-none">
            <div className="selmeter" aria-live="polite">
              {selectedWords.length}/10 selected
            </div>

            {selectedWords.length === 10 && !generatedSoul && (
              <div className="cta pointer-events-auto">
                <button onClick={finalizeSoul} className="btn" disabled={loading}>
                  {loading ? 'Weaving your soul…' : 'Generate soul'}
                </button>
              </div>
            )}

            {generatedSoul && (
              <div className="soulcard pointer-events-auto" role="status" aria-live="polite">
                <p className="kicker">Your soul has been forged. Remember it.</p>
                <p className="text">{generatedSoul}</p>
              </div>
            )}
          </div>
        )}

        <style>{`
          .ecodia-star-ui {
            --g1:#396041; --g2:#7FD069; --g3:#F4D35E;
            --ink:#0e1410; --muted:rgba(14,20,16,.78);
            --edge:rgba(0,0,0,.10); --shadow:0 10px 28px rgba(0,0,0,.20);
            font-family:"Comfortaa", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            position:absolute; inset:0; display:grid; place-items:end center;
            padding: 0 16px 20px; color:var(--ink);
          }
          .selmeter {
            position:absolute; top:14px; left:50%; transform:translateX(-50%);
            font-family:"Fjalla One","Comfortaa",ui-sans-serif;
            font-size:.9rem; color:rgba(14,20,16,.85);
            background: linear-gradient(180deg, rgba(0,0,0,.06), rgba(0,0,0,.03));
            border:1px solid var(--edge);
            padding:.28rem .6rem; border-radius:999px;
            backdrop-filter: blur(6px) saturate(1.02);
          }
          .cta { display:grid; place-items:center; gap:.5rem; margin-bottom:10px; }
          .btn {
            position:relative; display:inline-flex; align-items:center; justify-content:center; gap:.55rem;
            min-height: 44px; padding:.95rem 1.2rem; width:min(100%, 720px);
            border-radius:999px; color:#fff; text-decoration:none; font-weight:600;
            background:
              radial-gradient(120% 140% at 15% 15%, rgba(255,255,255,.22) 0%, transparent 55%),
              linear-gradient(135deg, var(--g1) 0%, var(--g2) 60%, var(--g3) 100%);
            border:1px solid rgba(0,0,0,.25);
            box-shadow: var(--shadow), inset 0 0 0 1px rgba(255,255,255,.10);
            overflow:hidden; transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;
            isolation:isolate; cursor:pointer;
          }
          .btn:hover { transform: translateY(-1px) scale(1.02); filter:saturate(1.05); }
          .btn:focus-visible { outline:none; box-shadow: 0 0 0 2px #000, 0 0 0 5px rgba(127,208,105,.55); }
          .btn::after {
            content:""; position:absolute; inset:0; border-radius:inherit; pointer-events:none;
            background: linear-gradient(115deg, transparent 0%, rgba(255,255,255,.25) 12%, rgba(255,255,255,.7) 18%, rgba(255,255,255,.25) 24%, transparent 30%);
            transform: translateX(-140%); transition: transform .6s ease;
          }
          .btn:hover::after { transform: translateX(140%); }
          .btn[disabled] { opacity:.85; cursor:not-allowed; filter:grayscale(.05); }
          .soulcard {
            margin-top:10px; text-align:center;
            border:1px solid var(--edge); border-radius:16px;
            background: linear-gradient(180deg, rgba(255,255,255,.75), rgba(255,255,255,.55)) padding-box, rgba(255,255,255,.55);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.55), var(--shadow);
            backdrop-filter: blur(8px) saturate(1.02);
            padding: .8rem 1rem; color:var(--ink); max-width: min(92vw, 720px);
          }
          .soulcard .kicker {
            font-size:.78rem; letter-spacing:.25px; margin:0 0 .2rem;
            font-family:"Fjalla One","Comfortaa",ui-sans-serif; color:rgba(14,20,16,.7);
          }
          .soulcard .text {
            font-size:1rem; letter-spacing:.2px; font-family:"Comfortaa", ui-sans-serif;
          }
        `}</style>
      </div>
    </>
  );
}
