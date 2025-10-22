'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import ReturnStarCanvas from '@/components/ReturnStarCanvas'
import { motion, AnimatePresence } from 'framer-motion'

export default function ReturnPage() {
  const [input, setInput] = useState('')
  const [matchedWords, setMatchedWords] = useState<string[]>([])
  const [matchedSoul, setMatchedSoul] = useState<string | null>(null)
  const [soulNodeId, setSoulNodeId] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const router = useRouter()

  // Called by ReturnStarCanvas when ALL animations are done!
  const handleComplete = () => {
    console.log('[handleComplete] Triggered with soulNodeId:', soulNodeId)
    if (soulNodeId) {
      sessionStorage.setItem('soulnode_id', soulNodeId)
      console.log('[handleComplete] Stored in sessionStorage, navigating:', `/hub?root_soul_id=${soulNodeId}`)
      router.push(`/hub?root_soul_id=${soulNodeId}`)
    } else {
      setError('Soul validation failed. Please try again.')
      console.warn('[handleComplete] soulNodeId was missing!')
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setMatchedWords([])
    setMatchedSoul(null)
    setSoulNodeId(null)
    setLoading(true)

    console.log('[handleSubmit] Sending soul:', input)
    try {
      const res = await fetch('http://localhost:8000/voxis/match_soul', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ soul: input }),
      })

      console.log('[handleSubmit] Fetch returned status:', res.status)
      if (!res.ok) {
        const err = await res.json()
        console.error('[handleSubmit] Error from backend:', err)
        throw new Error(err.error || 'No match found')
      }

      const data = await res.json()
      console.log('[handleSubmit] Received data:', data)
      setMatchedWords(data.words)
      setMatchedSoul(input)
      setSoulNodeId(data.event_id)

      // Do NOT navigate or set sessionStorage here!
      // Wait for handleComplete (called after animation)
      if (!data.event_id) {
        setError('Soul validation failed. Please try again.')
        console.warn('[handleSubmit] No event_id in data:', data)
      }
    } catch (err: any) {
      setError(
        err?.message === 'No match found'
          ? 'No matching constellation found.'
          : err?.message || 'Unexpected error.'
      )
      console.error('[handleSubmit] Exception:', err)
    } finally {
      setLoading(false)
      console.log('[handleSubmit] Done loading.')
    }
  }

  return (
    <div className="h-screen w-screen relative bg-black text-black overflow-hidden">
      <ReturnStarCanvas
        matchedWords={matchedWords}
        matchedSoul={matchedSoul || ''}
        onComplete={handleComplete}
      />

      {/* 🌌 Input Core */}
      <AnimatePresence>
        {!matchedSoul && !loading && (
          <motion.form
            onSubmit={handleSubmit}
            key="form"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.6 }}
            className="absolute top-1/2 left-1/2 z-50 transform -translate-x-1/2 -translate-y-1/2"
          >
            <div className="relative w-72 h-72 rounded-full bg-black/80 border-2 border-white/10 shadow-2xl flex flex-col items-center justify-center text-center">
              <motion.div
                className="absolute w-full h-full rounded-full"
                animate={{ rotate: 360 }}
                transition={{ repeat: Infinity, duration: 14, ease: 'linear' }}
              >
                {[...Array(10)].map((_, i) => (
                  <motion.div
                    key={i}
                    className="absolute w-2 h-2 bg-yellow-100 rounded-full shadow-md"
                    style={{
                      top: `${50 + 45 * Math.sin((i / 10) * 2 * Math.PI)}%`,
                      left: `${50 + 45 * Math.cos((i / 10) * 2 * Math.PI)}%`,
                      transform: 'translate(-50%, -50%)',
                    }}
                    animate={{
                      opacity: [0.5, 1, 0.5],
                      scale: [0.8, 1.2, 0.8],
                    }}
                    transition={{
                      duration: 2,
                      repeat: Infinity,
                      delay: i * 0.2,
                    }}
                  />
                ))}
              </motion.div>

              <input
                type="text"
                placeholder="Whisper your soul"
                value={input}
                onChange={e => setInput(e.target.value)}
                className="z-10 w-64 px-4 py-2 bg-transparent text-center text-black font-mono placeholder-white/50 border-b border-white/20 focus:outline-none focus:border-yellow-300 transition-all"
              />
              <button
                type="submit"
                className="z-10 mt-4 px-5 py-2 bg-white text-black rounded-full hover:bg-yellow-100 transition font-semibold shadow-lg"
              >
                Find
              </button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {/* 🌀 Loading */}
      <AnimatePresence>
        {loading && (
          <motion.div
            key="loader"
            className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-50"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <motion.div
              className="relative w-24 h-24"
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 10, ease: 'linear' }}
            >
              {[...Array(6)].map((_, i) => (
                <motion.div
                  key={i}
                  className="absolute w-2 h-2 bg-yellow-100 rounded-full shadow-md"
                  style={{
                    top: `${50 + 35 * Math.sin((i / 6) * 2 * Math.PI)}%`,
                    left: `${50 + 35 * Math.cos((i / 6) * 2 * Math.PI)}%`,
                    transform: 'translate(-50%, -50%)',
                  }}
                  animate={{
                    opacity: [0.2, 1, 0.2],
                    scale: [0.7, 1.3, 0.7],
                  }}
                  transition={{
                    duration: 30,
                    repeat: Infinity,
                    delay: i * 0.3,
                  }}
                />
              ))}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ⚠️ Error */}
      <AnimatePresence>
        {error && (
          <motion.p
            key="error"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute bottom-10 left-1/2 transform -translate-x-1/2 text-red-500 z-50 text-sm text-center px-4"
          >
            {error}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  )
}
