// ✅ 3D ReturnStarCanvas with full soul highlighting
'use client'

import { useEffect, useRef, useState, useMemo, Suspense } from 'react'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import { motion } from 'framer-motion'

interface Star {
  id: string
  position: [number, number, number]
  size: number
  glow: number
  word: string
  ref: React.MutableRefObject<THREE.Mesh | null>
}

interface ReturnStarCanvasProps {
  matchedWords: unknown
  matchedSoul?: string
  onComplete?: () => void
}

const PLACEHOLDER_WORDS: string[] = [
  'seed', 'leaf', 'bloom', 'tree', 'root',
  'river', 'soil', 'hill', 'stone', 'cloud',
  'meadow', 'wave', 'sand', 'forest', 'branch',
  'rain', 'light', 'wind', 'field', 'shell',
  'start', 'shift', 'move', 'turn', 'rise',
  'flow', 'open', 'drop', 'bend', 'carry',
  'path', 'edge', 'step', 'reach', 'grow',
  'cross', 'fall', 'touch', 'pass', 'follow',
  'thought', 'truth', 'voice', 'dream', 'focus',
  'pause', 'breathe', 'feel', 'sense', 'know',
  'learn', 'ask', 'choose', 'notice', 'wait',
  'face', 'rest', 'reflect', 'remember', 'shift',
  'care', 'love', 'trust', 'joy', 'hope',
  'calm', 'kind', 'warm', 'safe', 'soft',
  'reach', 'hold', 'share', 'join', 'give',
  'listen', 'watch', 'stay', 'show', 'offer',
  'walk', 'meet', 'gather', 'build', 'learn',
  'create', 'hold', 'bridge', 'stand', 'belong',
  'circle', 'team', 'hands', 'story', 'name',
  'home', 'guide', 'return', 'help', 'call'
]

function StarMesh({ star, isMatch }: { star: Star; isMatch: boolean }) {
  useFrame(({ clock }) => {
    const t = clock.getElapsedTime()
    const pulse = 1 + Math.sin(t * 2 + star.size) * 0.3
    if (star.ref.current) {
      star.ref.current.scale.set(pulse, pulse, pulse)
    }
  })

  return (
    <mesh ref={star.ref} position={star.position}>
      <sphereGeometry args={[star.size / 10, 12, 12]} />
      <meshStandardMaterial
        color={isMatch ? '#f4d35e' : '#ffffff'}
        emissive={isMatch ? '#f4d35e' : '#ffffff'}
        emissiveIntensity={isMatch ? 6 : 2}
        toneMapped={false}
      />
    </mesh>
  )
}

function ReturnStarCanvas3D({ matchedWords, matchedSoul, onComplete }: ReturnStarCanvasProps) {
  const [stars, setStars] = useState<Star[]>([])
  const [highlighted, setHighlighted] = useState<Set<string>>(new Set())
  const [fadeOut, setFadeOut] = useState(false)

  const activeWords: string[] = useMemo(() => {
    return Array.isArray(matchedWords)
      ? matchedWords.filter((w): w is string => typeof w === 'string')
      : []
  }, [matchedWords])

  useEffect(() => {
    const generated: Star[] = Array.from({ length: 100 }).map((_, i) => {
      const size = Math.random() * 6 + 3
      return {
        id: `star-${i}`,
        position: [
          (Math.random() - 0.5) * 200,
          (Math.random() - 0.5) * 200,
          (Math.random() - 0.5) * 200,
        ],
        size,
        glow: size * 6,
        word: PLACEHOLDER_WORDS[i % PLACEHOLDER_WORDS.length],
        ref: { current: null },
      }
    })
    setStars(generated)
  }, [])

  useEffect(() => {
    const matchedIds = new Set(
      stars.filter(s => activeWords.includes(s.word)).map(s => s.id)
    )
    setHighlighted(matchedIds)
  }, [activeWords, stars])

  useEffect(() => {
    if (matchedSoul) {
      const startFade = setTimeout(() => setFadeOut(true), 4000)
      const triggerExit = setTimeout(() => onComplete?.(), 6000)
      return () => {
        clearTimeout(startFade)
        clearTimeout(triggerExit)
      }
    }
  }, [matchedSoul, onComplete])

  return (
    <main className="fixed inset-0 w-screen h-screen m-0 p-0 overflow-hidden bg-black">
      <Suspense fallback={<div className="text-black">Loading constellation...</div>}>
        <Canvas camera={{ position: [0, 0, 300], fov: 75 }}>
          <ambientLight intensity={0.3} />
          <pointLight position={[20, 40, 80]} intensity={2.5} />
          {stars.map((star) => (
            <StarMesh
              key={star.id}
              star={star}
              isMatch={highlighted.has(star.id)}
            />
          ))}
          <OrbitControls autoRotate autoRotateSpeed={4} enablePan enableZoom enableRotate />
        </Canvas>

        {matchedSoul && !fadeOut && (
          <motion.div
            className="absolute top-[10%] left-1/2 transform -translate-x-1/2 text-center z-30"
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 2 }}
          >
            <motion.span
              className="font-mono text-xl md:text-3xl text-yellow-100"
              animate={{ opacity: [0.4, 1, 0.4] }}
              transition={{ repeat: Infinity, duration: 3 }}
              style={{ textShadow: '0 0 15px #f4d35e, 0 0 30px #f4d35e66' }}
            >
              {matchedSoul}
            </motion.span>
          </motion.div>
        )}
      </Suspense>
    </main>
  )
}

export default ReturnStarCanvas3D
