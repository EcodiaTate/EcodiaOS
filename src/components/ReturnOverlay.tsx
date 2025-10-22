'use client'

import React, { useEffect, useRef, useState } from 'react'
import { useModeStore } from '@/stores/useModeStore'
import { useSoulStore } from '@/stores/useSoulStore'
import { BackToEcodiaButton, BackToRootButton } from '@/components/ui'

/** pointer parallax for card + shine */
function usePanelParallax() {
  const ref = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect()
      const x = (e.clientX - r.left) / r.width - 0.5
      const y = (e.clientY - r.top) / r.height - 0.5
      el.style.setProperty('--tiltX', `${-(y * 1.8)}deg`)
      el.style.setProperty('--tiltY', `${x * 1.8}deg`)
      el.style.setProperty('--shineX', `${e.clientX - r.left}px`)
      el.style.setProperty('--shineY', `${e.clientY - r.top}px`)
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])
  return ref
}

export default function ReturnOverlay() {
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const { matchedWords, setMatchedSoul, setUserUuid } = useSoulStore()
  const setMode = useModeStore((s) => s.setMode)

  const panelRef = usePanelParallax()

  // resume from session if present
  useEffect(() => {
    const id = sessionStorage.getItem('soulnode_id')
    const words = sessionStorage.getItem('soulnode_words')
    if (id && words) {
      try {
        setMatchedSoul(id, JSON.parse(words))
        localStorage.setItem('user_uuid', id)
        setUserUuid(id)
        setTimeout(() => setMode('hub'), 100)
      } catch (e) {
        console.warn('Bad session-stored soul:', e)
      }
    }
  }, [setMode, setMatchedSoul, setUserUuid])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return
    setLoading(true)
    setError('')

    try {
      const res = await fetch('/api/voxis/match_soul', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ soul: input, debug: 0 }),
      })
      const data = await res.json()
      if (!res.ok || !data.words) throw new Error(data.error || 'No match found')

      const soulId: string = data.uuid || data.key_id || data.event_id || input

      sessionStorage.setItem('soulnode_id', soulId)
      sessionStorage.setItem('soulnode_words', JSON.stringify(data.words))
      localStorage.setItem('user_uuid', soulId)

      setMatchedSoul(soulId, data.words)
      setUserUuid(soulId)

      setTimeout(() => setMode('hub'), 900)
    } catch (err: any) {
      setError(err.message || 'Failed to match soul')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="return-root">
      {/* ambient accents (vignette + grid) */}
      <div className="return-ambient" aria-hidden="true">
        <div className="return-vignette" />
        <div className="return-grid" />
      </div>

      {/* floating controls */}
      <div className="return-topbar">
        <BackToRootButton />
        <BackToEcodiaButton />
      </div>

      {/* panel */}
      <section aria-label="Return to Ecodia" className="return-wrap">
        <div ref={panelRef} className="return-panel" role="dialog" aria-modal="true">
          <div className="return-border" aria-hidden="true" />
          <div className="return-shine" aria-hidden="true" />

          <header className="return-header">
            <div className="return-icon" aria-hidden>⟲</div>
            <h1 className="return-title">Return</h1>
            <p className="return-sub">Reconnect with your soul key</p>
          </header>

          {!matchedWords ? (
            <form onSubmit={handleSubmit} className="return-form" aria-label="Match your soul">
              <label htmlFor="soulnode" className="sr-only">Soul</label>

              <div className={`return-inputWrap ${input ? 'is-typing' : ''} ${error ? 'has-error' : ''}`}>
                <input
                  id="soulnode"
                  className="return-input"
                  placeholder="whisper your soul…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  autoFocus
                  autoComplete="off"
                  spellCheck={false}
                  aria-invalid={Boolean(error) || undefined}
                  aria-describedby={error ? 'soulnode-error' : 'soulnode-hint'}
                />
                <div className="return-inputGlow" aria-hidden />
              </div>

              <p id="soulnode-hint" className="return-hint">
                Paste or type your Ecodia soul phrase / key. It never leaves this page until you submit.
              </p>

              <button
                className="return-btn"
                type="submit"
                disabled={loading}
                aria-busy={loading || undefined}
              >
                <span className="return-btnGlow" aria-hidden />
                {loading ? 'Listening to Ecodia…' : 'Match'}
              </button>

              {error && (
                <p id="soulnode-error" className="return-error" role="alert">
                  {error}
                </p>
              )}
            </form>
          ) : (
            <div className="return-matched" aria-live="polite">
              Soul found. Taking you to the hub…
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
