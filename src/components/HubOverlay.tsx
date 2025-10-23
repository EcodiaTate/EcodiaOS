'use client'

import React, { useEffect, useRef } from 'react'
import { useModeStore } from '@/stores/useModeStore'
import { BackToRootButton, BackToEcodiaButton, ContactEcodiaButton } from '@/components/ui'

/** pointer parallax + shine */
function usePanelParallax() {
  const ref = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect()
      const x = (e.clientX - r.left) / r.width - 0.5
      const y = (e.clientY - r.top) / r.height - 0.5
      el.style.setProperty('--tiltX', `${-(y * 1.6)}deg`)
      el.style.setProperty('--tiltY', `${x * 1.6}deg`)
      el.style.setProperty('--shineX', `${e.clientX - r.left}px`)
      el.style.setProperty('--shineY', `${e.clientY - r.top}px`)
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])
  return ref
}

export default function HubOverlay() {
  const setMode = useModeStore((s) => s.setMode)
  const panelRef = usePanelParallax()

  return (
    <div className="hub-root">
      {/* Ambient accents (matches other overlays) */}
      <div className="hub-ambient" aria-hidden="true">
        <div className="hub-vignette" />
        <div className="hub-grid" />
      </div>

      {/* Hub Panel */}
      <section aria-label="Ecodia Hub Overlay" className="hub-wrap">
        <div ref={panelRef} className="hub-panel" role="dialog" aria-modal="true">
          <div className="hub-border" aria-hidden="true" />
          <div className="hub-shine" aria-hidden="true" />

          {/* HEADER — image smaller, circular, centered */}
          <header className="hub-header text-center flex flex-col items-center">
            <img
              src="/assets/button.png"
              alt="Ecodia"
              className="
                mx-auto mb-5
                size-16             
                rounded-full
                object-cover
                ring-2 ring-white/40 shadow-lg
              "
            />
            <h1 className="hub-title">Explore</h1>
            <p className="hub-sub">Choose how you want to meet the mind</p>
          </header>

          <div className="hub-actions" role="group" aria-label="Primary actions">
            <button
              className="hub-btn"
              onClick={() => setMode('talk')}
              aria-label="Talk to Ecodia"
            >
              <span className="hub-btnGlow" aria-hidden />
              Talk to Ecodia
            </button>

            <button
              className="hub-btn hub-btn--secondary"
              onClick={() => setMode('guide')}
              aria-label="Guide Ecodia"
            >
              <span className="hub-btnGlow" aria-hidden />
              Guide Ecodia
            </button>
          </div>
        </div>
      </section>

      {/* Floating controls (top-right, always clickable) */}
      <div className="hub-controls pointer-events-auto">
        <BackToRootButton />
        <ContactEcodiaButton />
        <BackToEcodiaButton />
      </div>
    </div>
  )
}
