'use client'

import React, { useEffect, useState } from 'react'
import { useModeStore } from '@/stores/useModeStore'
import { useSoulStore } from '@/stores/useSoulStore'
import { BackToEcodiaButton, BackToRootButton } from '@/components/ui'

export default function ReturnOverlay() {
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const { matchedWords, setMatchedSoul, setUserUuid } = useSoulStore()
  const setMode = useModeStore((s) => s.setMode)

  useEffect(() => {
    // Resume from session if present
    const id = sessionStorage.getItem('soulnode_id')
    const words = sessionStorage.getItem('soulnode_words')
    if (id && words) {
      try {
        setMatchedSoul(id, JSON.parse(words))
        localStorage.setItem('user_uuid', id) // for Talk overlay pickup
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

      setTimeout(() => setMode('hub'), 1200)
    } catch (err: any) {
      setError(err.message || 'Failed to match soul')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="retorno">
      {/* Floating controls */}
      <div className="retorno-topbar">
        <BackToRootButton />
        <BackToEcodiaButton />
      </div>

      {/* Panel */}
      <section aria-label="Return to Ecodia" className="retorno-wrap">
        <div className="retorno-panel" role="dialog" aria-modal="true">
          <h1 className="retorno-title">Return</h1>

          {!matchedWords ? (
            <form onSubmit={handleSubmit} className="retorno-form" aria-label="Match your soul">
              <label htmlFor="soulnode" className="sr-only">Soul</label>
              <input
                id="soulnode"
                className="retorno-input"
                placeholder="whisper your soul..."
                value={input}
                onChange={(e) => setInput(e.target.value)}
                autoFocus
                autoComplete="off"
                spellCheck={false}
                aria-invalid={Boolean(error) || undefined}
                aria-describedby={error ? 'soulnode-error' : undefined}
              />

              <button className="retorno-btn" type="submit" disabled={loading} aria-busy={loading}>
                {loading ? 'Listening to Ecodia…' : 'Match'}
              </button>

              {error && (
                <p id="soulnode-error" className="retorno-error" role="alert">
                  {error}
                </p>
              )}
            </form>
          ) : (
            <div className="retorno-matched">Soul found. Taking you to the hub…</div>
          )}
        </div>
      </section>
    </div>
  )
}
