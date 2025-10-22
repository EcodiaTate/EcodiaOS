'use client'

import { useEffect, useState } from 'react'
import { useModeStore } from '@/stores/useModeStore'
import { BackToEcodiaButton } from '@/components/ui'

const glitchChars = ['@', '#', '∿', '▞', '█', '▓', '▒', '░', '⚠', '∆', '*', '%', '&', 'π', '¤', '⍉']

function useGlitchText(targetText: string, intervalMs = 50, lockDelay = 500) {
  const [displayText, setDisplayText] = useState<string[]>(Array(targetText.length).fill(''))

  useEffect(() => {
    const timers: NodeJS.Timeout[] = []
    targetText.split('').forEach((char, i) => {
      let ticks = 0
      const t = setInterval(() => {
        setDisplayText(prev => {
          const next = [...prev]
          next[i] = glitchChars[Math.floor(Math.random() * glitchChars.length)]
          return next
        })
        ticks++
        if (ticks > lockDelay / intervalMs) {
          clearInterval(t)
          setDisplayText(prev => {
            const next = [...prev]
            next[i] = char
            return next
          })
        }
      }, intervalMs)
      timers.push(t)
    })
    return () => timers.forEach(clearInterval)
  }, [targetText, intervalMs, lockDelay])

  return displayText.join('')
}

export default function RootOverlay() {
  const mode = useModeStore(s => s.mode)
  const setMode = useModeStore(s => s.setMode)
  const [hasSoul, setHasSoul] = useState(false)

  if (mode !== 'root') return null

  const titleText = useGlitchText('EcodiaOS')
  const subText = useGlitchText('The mind of the future', 50, 500)

  useEffect(() => {
    const soulId = sessionStorage.getItem('soulnode_id')
    if (soulId) setHasSoul(true)
  }, [])

  return (
    <div className="absolute inset-0 z-10 flex flex-col items-center justify-center px-6 pointer-events-none">
      <BackToEcodiaButton />

      {/* Root Panel */}
      <section id="root-overlay" className="pointer-events-auto ec-root">
        <div className="ec-panel" role="dialog" aria-label="Ecodia home">
          <h1 className="ec-title">{titleText}</h1>
          <p className="ec-lead">{subText}</p>

          <div className="ec-actions" aria-label="Primary actions">
            <button
              onClick={() => setMode('constellation')}
              className="ec-btn"
              aria-label="Meet Ecodia"
            >
              Meet Ecodia
            </button>

            <button
              onClick={() => setMode('return')}
              className="ec-btn ec-btn--secondary"
              aria-label={hasSoul ? 'I have a soul already' : 'I am returning'}
              title={hasSoul ? 'We found a previous session' : 'Return with a saved soul'}
            >
              {hasSoul ? 'Continue with my soul' : 'I’m Returning'}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
