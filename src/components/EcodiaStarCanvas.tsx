'use client'

import { useRef, useState, useEffect, useMemo } from 'react'
import { Canvas, useThree, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import * as THREE from 'three'

// Zustand Stores for state management
import { useSoulStore } from '@/stores/useSoulStore';
import { useModeStore } from '@/stores/useModeStore'
import { useNodeStore } from '@/stores/useNodeStore'

// Canvas Components
import ExtendLinesClient from './ExtendLinesClient'
import CameraRig from './CameraRig'
import CoreArcConnections from './CoreArcConnections'
import BrainNode from './BrainNode'
import ConstellationStar from './ConstellationStar'
import ConnectionLine from './ConnectionLine'
import ConstellationConnections from './ConstellationConnections'
import PulseManager from './PulseController'
import EcodiaCore from './EcodiaCore'

// Data and Utils
import PLACEHOLDER_WORDS from '@/lib/placholderWords'
import {
  generateNodes,
  generateConnections,
  PulseConnection,
  Node as GraphNode,
  Star,
} from '@/lib/graphUtils'

type CanvasNode = GraphNode & { isCore?: boolean; system: string }

function ControlsUpdater() {
  const controls = useThree((state) => state.controls) as OrbitControlsImpl
  useFrame(() => {
    controls?.update()
  })
  return null
}

export default function EcodiaStarCanvas() {
  const nodesRef = useRef<CanvasNode[]>([])
  const connectionsRef = useRef<PulseConnection[]>([])
  const [connections, setConnections] = useState<PulseConnection[]>([])
  const adjacencyMap = useRef<Record<number, number[]>>({})
  const coreIndex = 0

  // --- Zustand Store Integration ---
  const { selectedWords, toggleWordSelection, setMatchedSoul, clearSoul } = useSoulStore();
  const mode = useModeStore(s => s.mode)
  const setMode = useModeStore(s => s.setMode)
  const { registerNode, clearNodes } = useNodeStore()
  
  const [ready, setReady] = useState(false)
  const [loading, setLoading] = useState(false)
  const [generatedSoul, setGeneratedSoul] = useState<string | null>(null)

  const isAutoRotateEnabled = mode !== 'constellation'
  const isUserControlEnabled = mode === 'constellation'

  // --- MOVED HOOKS TO TOP LEVEL ---
  // All useMemo, useState, useEffect, etc. must be called before any conditional returns.
  const coreEdges = useMemo(() => {
    return connectionsRef.current
      .filter(c => c.a === coreIndex || c.b === coreIndex)
      .map(c => ({ source: c.a, target: c.b, type: 'literal' as const }))
  }, [connections])

  const dedupedConnections = useMemo(() => {
    const seen = new Set<string>()
    return connections.filter((c) => {
      if (c.a === coreIndex || c.b === coreIndex) return false
      const [a, b] = [c.a, c.b].sort((x, y) => x - y)
      const key = `${a}-${b}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  }, [connections])
  
  const selectedStars = useMemo(() => {
      return nodesRef.current.filter(n => n.isStar && selectedWords.includes(n.word!)) as Star[];
  }, [selectedWords]);
  // --- END OF HOOKS SECTION ---

  useEffect(() => {
    clearSoul();

    const stars: Star[] = PLACEHOLDER_WORDS.map((word, i) => ({
      id: `star-${i}`,
      position: i === 0 ? [0, 0, 0] : [(Math.random() - 0.5) * 4000, (Math.random() - 0.5) * 4000, (Math.random() - 0.5) * 4000],
      word,
      size: Math.random() * 30 + 50,
      glow: Math.random() * 10 + 5,
      ...(i === 0 ? { isCore: true } : { isStar: true }),
    }))

    const nodes = generateNodes(stars) as CanvasNode[]
    const generatedConnections = generateConnections(nodes, adjacencyMap.current)

    nodesRef.current = nodes
    connectionsRef.current = generatedConnections
    setConnections(generatedConnections)
    
    clearNodes()
    stars.forEach(s => registerNode(s.word, new THREE.Vector3(...s.position)))

    setReady(true)
  }, [clearNodes, clearSoul, registerNode])

  const handleSelect = (star: Star) => {
    if (mode === 'constellation' && !generatedSoul) {
        toggleWordSelection(star.word, 10);
    }
  };

  const finalizeSoul = async () => {
    if (selectedWords.length !== 10) return
    setLoading(true)
    setGeneratedSoul(null)
  
    try {
      const response = await fetch('/api/voxis/generate-soul', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ words: selectedWords }),
      })
      const data = await response.json()
      if (!response.ok || !data.soul) throw new Error(data.error || 'Failed to generate soul')
  
      const soulId = data.event_id || data.key_id || ''
      sessionStorage.setItem('soulnode_id', soulId)
      sessionStorage.setItem('soulnode_words', JSON.stringify(data.words || selectedWords))
      sessionStorage.setItem('soulnode_plaintext', data.soul)
  
      setMatchedSoul(soulId, data.words || selectedWords)
      setGeneratedSoul(data.soul)

      setTimeout(() => {
        setMode('hub');
      }, 4000);

    } catch (err: any) {
      console.error('Soul generation failed:', err)
      setGeneratedSoul(`Error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }
  
  if (!ready || !nodesRef.current[coreIndex]) return null

  return (
    <>
      <ExtendLinesClient />
      <div className="relative w-full h-screen">
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@300;400;700&family=Fjalla+One&display=swap"
          rel="stylesheet"
        />

        <Canvas
          camera={{ position: [0, 0, 10000], fov: 65, near: 0.1, far: 13000 }}
          gl={{ logarithmicDepthBuffer: true }}
        >
          <color attach="background" args={['#292828']} />

          <CoreArcConnections
            nodes={nodesRef.current}
            edges={coreEdges}
            coreIndex={coreIndex}
            connectionsRef={connectionsRef.current}
          />
          <EcodiaCore />
          <CameraRig />
          <PulseManager
            nodesRef={nodesRef.current}
            connectionsRef={connectionsRef.current}
            adjacencyMap={adjacencyMap.current}
          />

          <OrbitControls
            autoRotate={isAutoRotateEnabled}
            autoRotateSpeed={0.2}
            enableDamping
            dampingFactor={0.05}
            rotateSpeed={0.6}
            enablePan={isUserControlEnabled}
            enableZoom={isUserControlEnabled}
            enableRotate={true}
            makeDefault
          />

          <ControlsUpdater />

          {mode === 'constellation' &&
            nodesRef.current.filter(n => n.isStar).map(n => (
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

          {mode === 'constellation' && (
            <ConstellationConnections selected={selectedStars} />
          )}

          {nodesRef.current.map((node, i) => (
            <BrainNode key={i} node={node} />
          ))}

          {dedupedConnections.map(connection => (
            <ConnectionLine
              key={`${connection.a}-${connection.b}`}
              connection={connection}
              nodesRef={nodesRef.current}
            />
          ))}
        </Canvas>

        {mode === 'constellation' && (
          <div className="ecodia-star-ui pointer-events-none">
            <div className="selmeter" aria-live="polite">
              {selectedWords.length}/10 selected
            </div>

            {selectedWords.length === 10 && !generatedSoul && (
              <div className="cta pointer-events-auto">
                <button
                  onClick={finalizeSoul}
                  className="btn"
                  disabled={loading}
                >
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
            --ink:#e9f4ec; --muted:rgba(255,255,255,.78);
            --edge:rgba(255,255,255,.10); --shadow:0 10px 28px rgba(0,0,0,.45);
            font-family:"Comfortaa", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            position:absolute; inset:0; display:grid; place-items:end center;
            padding: 0 16px 20px; color:var(--ink);
          }
          .selmeter {
            position:absolute; top:14px; left:50%; transform:translateX(-50%);
            font-family:"Fjalla One","Comfortaa",ui-sans-serif;
            font-size:.9rem; color:rgba(233,244,236,.85);
            background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.04));
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
              radial-gradient(120% 140% at 15% 15%, rgba(255,255,255,.12) 0%, transparent 55%),
              linear-gradient(135deg, var(--g1) 0%, var(--g2) 60%, var(--g3) 100%);
            border:1px solid rgba(0,0,0,.4);
            box-shadow: var(--shadow), inset 0 0 0 1px rgba(255,255,255,.06);
            overflow:hidden; transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;
            isolation:isolate; cursor:pointer;
          }
          .btn:hover { transform: translateY(-1px) scale(1.02); filter:saturate(1.05); }
          .btn:focus-visible { outline:none; box-shadow: 0 0 0 2px #000, 0 0 0 5px rgba(127,208,105,.65); }
          .btn::after {
            content:""; position:absolute; inset:0; border-radius:inherit; pointer-events:none;
            background: linear-gradient(115deg, transparent 0%, rgba(255,255,255,.18) 12%, rgba(255,255,255,.6) 18%, rgba(255,255,255,.2) 24%, transparent 30%);
            transform: translateX(-140%); transition: transform .6s ease;
          }
          .btn:hover::after { transform: translateX(140%); }
          .btn[disabled] { opacity:.75; cursor:not-allowed; filter:grayscale(.1); }
          .soulcard {
            margin-top:10px; text-align:center;
            border:1px solid var(--edge); border-radius:16px;
            background: linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.04)) padding-box, rgba(14,20,16,.35);
            box-shadow: inset 0 0 0 1px rgba(255,255,255,.03), var(--shadow);
            backdrop-filter: blur(8px) saturate(1.02);
            padding: .8rem 1rem; color:var(--ink); max-width: min(92vw, 720px);
          }
          .soulcard .kicker {
            font-size:.78rem; letter-spacing:.25px; margin:0 0 .2rem;
            font-family:"Fjalla One","Comfortaa",ui-sans-serif; color:rgba(233,244,236,.7);
          }
          .soulcard .text {
            font-size:1rem; letter-spacing:.2px; font-family:"Comfortaa", ui-sans-serif;
          }
        `}</style>
      </div>
    </>
  )
}