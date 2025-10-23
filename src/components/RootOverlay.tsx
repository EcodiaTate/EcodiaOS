'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { useModeStore } from '@/stores/useModeStore'
import { BackToEcodiaButton } from '@/components/ui'
import {SignInWithEcodiaButton} from "@/components/auth/SignInWithEcodiaButton"
/** Sunrise Solarpunk palette (mirrors canvas vibe) */
const PALETTE = {
  mint: '#7fd069',
  gold: '#f4d35e',
  pearl: '#f5f8f7',
  ink: '#0e1511',
  frost: 'rgba(255,255,255,0.6)',
}

/** Softer, bio-ish glyphs (less terminal noise) */
const bioChars = ['·','•','∙','○','◦','∘','✶','✳','❈','✷','✺','✴','△','◇','✧','✦']

/** Bio-glitch: per-char shimmer that locks to the real letter in a cascading wave */
function useBioGlitch(target: string, speed = 28, lockStagger = 22) {
  const [out, setOut] = useState<string[]>(() => Array.from({ length: target.length }, () => ''))
  const lockAt = useMemo(
    () => Array.from({ length: target.length }, (_, i) => Math.floor((i * lockStagger) / speed) + 8),
    [target.length, speed, lockStagger]
  )

  useEffect(() => {
    let t = 0
    const id = setInterval(() => {
      t++
      setOut((prev) => {
        const next = [...prev]
        for (let i = 0; i < target.length; i++) {
          if (t > lockAt[i]) next[i] = target[i]
          else next[i] = bioChars[(Math.random() * bioChars.length) | 0]
        }
        return next
      })
      if (t > Math.max(...lockAt) + 3) clearInterval(id)
    }, speed)
    return () => clearInterval(id)
  }, [target, speed, lockAt])

  return out.join('')
}

/** Gentle pointer parallax for the panel shine */
function usePointerParallax() {
  const ref = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect()
      const x = (e.clientX - r.left) / r.width - 0.5
      const y = (e.clientY - r.top) / r.height - 0.5
      el.style.setProperty('--tiltX', `${-(y * 2)}deg`)
      el.style.setProperty('--tiltY', `${x * 2}deg`)
      el.style.setProperty('--shineX', `${e.clientX - r.left}px`)
      el.style.setProperty('--shineY', `${e.clientY - r.top}px`)
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])
  return ref
}

export default function RootOverlay() {
  const mode = useModeStore((s) => s.mode)
  const setMode = useModeStore((s) => s.setMode)
  const [hasSoul, setHasSoul] = useState(false)

  if (mode !== 'root') return null

  const title = useBioGlitch('EcodiaOS', 26, 20)
  const subtitle = useBioGlitch('The mind of the future', 26, 18)
  const panelRef = usePointerParallax()

  useEffect(() => {
    const soulId = sessionStorage.getItem('soulnode_id')
    if (soulId) setHasSoul(true)
  }, [])

  return (
    <div
      className="absolute inset-0 z-10 flex items-center justify-center pointer-events-none"
      aria-label="Ecodia Overlay"
    >
      <BackToEcodiaButton />

      {/* Ambient vignette + grid accents (subtle, complements canvas) */}
      <div className="absolute inset-0 pointer-events-none mix-blend-multiply">
        <div className="absolute inset-0 bg-[radial-gradient(1200px_600px_at_center,rgba(255,255,255,0.30),transparent_65%)]" />
        <div className="absolute inset-8 rounded-[28px] border border-white/30 [mask:linear-gradient(#000,transparent)]" />
        <div className="absolute inset-0 opacity-[0.07] [background:linear-gradient(to_right,transparent_49.5%,rgba(0,0,0,0.6)_50%,transparent_50.5%),linear-gradient(to_bottom,transparent_49.5%,rgba(0,0,0,0.6)_50%,transparent_50.5%)] background-size:40px_40px" />
      </div>

      {/* Root Panel */}
      <section id="root-overlay" className="pointer-events-auto ec-root">
        <div
          ref={panelRef}
          className="ec-panel group will-change-transform"
          role="dialog"
          aria-label="Ecodia home"
        >
          {/* Energy seam / gradient border */}
          <div className="ec-border" aria-hidden="true" />

          {/* Shine sweep */}
          <div className="ec-shine pointer-events-none" aria-hidden="true" />

          <h1 className="ec-title">
            <span className="sr-only">EcodiaOS</span>
            <span aria-hidden>{title}</span>
          </h1>

          <p className="ec-lead">{subtitle}</p>

          <div className="ec-actions" aria-label="Primary actions">

           <SignInWithEcodiaButton/>
          </div>
        </div>
      </section>
    </div>
  )
}
