'use client'

import React, { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useModeStore } from '@/stores/useModeStore'
import { useSoulStore } from '@/stores/useSoulStore'
import { useThemeStore } from '@/stores/useThemeStore'
import { BackToEcodiaButton, BackToRootButton } from '@/components/ui'

const CONSENT_KEY = 'constellationIntroAccepted:v2'
const MIN_DWELL_MS = 250               // minimum time the modal stays visible
const CANVAS_READY_FALLBACK_MS = 600   // failsafe if no ready event fires

export default function ConstellationOverlay() {
  // init from storage to avoid flicker
  const [hasAccepted, setHasAccepted] = useState<boolean>(() => {
    try { return localStorage.getItem(CONSENT_KEY) === 'true' } catch { return false }
  })

  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState<string>('')

  const setMode = useModeStore((s) => s.setMode)
  const { clearMatchedSoul, setMatchedSoul, selectedWords = [] } = useSoulStore() as any

  const theme = useThemeStore((s) => s.theme)
  const isLight = theme === 'light'

  // modal gating
  const [canvasReady, setCanvasReady] = useState(false)
  const [minDwellElapsed, setMinDwellElapsed] = useState(false)
  const shownAtRef = useRef<number | null>(null)

  // Clear any prior match on entry (once)
  useEffect(() => { clearMatchedSoul?.() }, [clearMatchedSoul])

  // Start the minimum dwell timer when the modal first shows
  useEffect(() => {
    if (!hasAccepted && shownAtRef.current == null) {
      shownAtRef.current = Date.now()
      const t = setTimeout(() => setMinDwellElapsed(true), MIN_DWELL_MS)
      return () => clearTimeout(t)
    }
  }, [hasAccepted])

  // Listen for canvas ready; also mark ready after a short fallback
  useEffect(() => {
    const markReady = () => setCanvasReady(true)
    window.addEventListener('constellation:ready', markReady, { once: true })
    const fallback = setTimeout(markReady, CANVAS_READY_FALLBACK_MS)
    return () => {
      window.removeEventListener('constellation:ready', markReady)
      clearTimeout(fallback)
    }
  }, [])

  // unlock if min dwell elapsed AND (canvas ready OR the fallback elapsed)
  const allowDismiss = (() => {
    if (!shownAtRef.current) return false
    const elapsed = Date.now() - shownAtRef.current
    return minDwellElapsed && (canvasReady || elapsed >= CANVAS_READY_FALLBACK_MS)
  })()

  const handleAccept = () => {
    if (!allowDismiss) return
    try { localStorage.setItem(CONSENT_KEY, 'true') } catch {}
    setHasAccepted(true)
  }

  const handleGenerate = async () => {
    if (!selectedWords?.length) return
    setGenerating(true)
    setError('')
    try {
      // NOTE: underscore route as requested
      const res = await fetch('/api/voxis/generate_soul', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ words: selectedWords }),
      })

      const data = await res.json()
      if (!res.ok || !data.soul) throw new Error(data.error || 'Failed to generate soul')

      const soulId = data.event_id || data.key_id || ''
      sessionStorage.setItem('soulnode_id', soulId)
      sessionStorage.setItem('soulnode_words', JSON.stringify(data.words || selectedWords))
      sessionStorage.setItem('soulnode_plaintext', data.soul)

      setMatchedSoul?.(soulId, data.words || selectedWords)
      setMode('hub')
    } catch (e: any) {
      setError(e?.message || 'An unexpected error occurred.')
    } finally {
      setGenerating(false)
    }
  }

  // Modal (explicit close only; gated by allowDismiss)
  if (!hasAccepted) {
    return (
      <div className="fixed inset-0 z-50 ecodia-modal-backdrop">
        <div className="ecodia-modal" role="dialog" aria-modal="true" aria-labelledby="constellation-title">
          <button
            className="ecodia-modal__close"
            aria-label="Close"
            title={!allowDismiss ? 'Preparing…' : 'Close'}
            onClick={handleAccept} // or: () => setMode('root')
            disabled={!allowDismiss}
          >
            ×
          </button>

          <h2 id="constellation-title" className="ecodia-modal__title">✨ Create Your Constellation</h2>

          <p className="ecodia-modal__body">
            Each of the white nodes represent a word the Ecodia values, but you don’t know which ones.
            Pick 10 nodes that feel right to you, and remember the soul you are given. This will be your password to Ecodia.
          </p>
          <p className="ecodia-modal__hint">
            Your selections are stored permanently for the purpose of this experience.
          </p>

          <button
            onClick={handleAccept}
            disabled={!allowDismiss}
            aria-disabled={!allowDismiss}
            className="ecodia-modal__cta"
            title={!allowDismiss ? 'Preparing…' : 'Let’s go'}
          >
            {!allowDismiss ? 'Preparing…' : 'Got it, let’s go'}
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className={`consto ${isLight ? 'consto--light' : 'consto--dark'}`}>
      {/* Back + info */}
      <button
        onClick={() => setMode('root')}
        className="consto-pill consto-pill--nav"
        aria-label="Back"
        title="Back"
      >
        ←
      </button>

      <button
        onClick={() =>
          alert(
            '🪐 Tap stars to select words. Pinch/scroll to zoom. Drag to move around. Select up to 10 stars before generating your constellation soul.'
          )
        }
        className="consto-pill consto-pill--info"
        aria-label="How it works"
        title="How it works"
      >
        ℹ
      </button>

      {/* Banner */}
      <motion.div
        layout
        className="consto-banner"
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 1.4, ease: 'easeOut' }}
      >
        <div className="consto-banner__wrap">
          <div className="consto-banner__glow" />
          <p className="consto-banner__text">✨ The stars remember. Create your constellation.</p>
        </div>
      </motion.div>

      <BackToRootButton />
      <BackToEcodiaButton />
    </div>
  )
}
