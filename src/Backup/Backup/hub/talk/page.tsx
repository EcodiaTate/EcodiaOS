'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import { useSearchParams } from 'next/navigation'
import { motion } from 'framer-motion'

export default function TalkPage() {
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([])
  const [loading, setLoading] = useState(false)
  const [soulNodeId, setSoulNodeId] = useState<string | null>(null)
  const [userId, setUserId] = useState<string>('user_anon')
  const [error, setError] = useState('')
  const [moodVars, setMoodVars] = useState({
    bgColor: '#060a07',
    fireflyColor: '#f4d35e',
    shadowColor: '#f4d35e',
    motionIntensity: 0.3,
  })

  const bottomRef = useRef<HTMLDivElement>(null)
  const searchParams = useSearchParams()

  useEffect(() => {
    let soulId = sessionStorage.getItem('soulnode_id')
    if (searchParams?.get('root_soul_id')) {
      soulId = searchParams.get('root_soul_id')
      if (soulId) sessionStorage.setItem('soulnode_id', soulId)
    }
    setSoulNodeId(soulId)
  }, [searchParams])

  useEffect(() => {
    async function fetchMood() {
      try {
        const res = await fetch(`http://localhost:8000/alive/interface_mood`)
        const data = await res.json()
        setMoodVars({
          bgColor: data.bgColor || '#060a07',
          fireflyColor: data.fireflyColor || '#f4d35e',
          shadowColor: data.shadowColor || '#f4d35e',
          motionIntensity: data.motionIntensity ?? 0.3,
        })
      } catch (err) {
        console.warn('Failed to fetch interface mood, using defaults.')
      }
    }
    fetchMood()
  }, [userId])

  const sendMessage = async () => {
    if (!input.trim()) return
    if (!soulNodeId) {
      setError('Session expired or soul not found. Please return and re-enter your soul soul.')
      return
    }

    setError('')
    const userMessage = { role: 'user', content: input.trim() }
    setMessages(prev => [...prev, userMessage])
    setInput('')
    setLoading(true)

    try {
      const res = await fetch('http://localhost:8000/alive/talk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_input: userMessage.content,
          user_id: userId,
          soul_event_id: soulNodeId,
        }),
      })
      const data = await res.json()
      setMessages(prev => [...prev, { role: 'ecodia', content: data.response }])
    } catch (e) {
      setMessages(prev => [...prev, { role: 'ecodia', content: '⚠️ Error responding.' }])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (!soulNodeId) {
    return (
      <div className="h-screen w-full bg-black text-black flex items-center justify-center">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-red-400 mb-2">Session not found</h1>
          <p className="text-black/70 mb-4">Please return to the soul soul screen and re-enter your soul.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative h-[calc(100vh-64px)] w-full text-black flex flex-col items-center justify-center overflow-hidden"
         style={{ backgroundColor: moodVars.bgColor }}>
      <AnimatedBackground {...moodVars} />

      <div className="w-full max-w-3xl flex-1 overflow-y-auto px-4 pt-4 pb-2 space-y-4 scrollbar-thin scrollbar-thumb-[#396041]/40 scrollbar-track-transparent z-10">
        {messages.map((msg, idx) => (
          <motion.div
            key={idx}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className={`group relative px-4 py-2 rounded-2xl shadow-sm md:shadow-md leading-relaxed tracking-wide text-sm md:text-base break-words whitespace-pre-wrap w-fit max-w-full ${
              msg.role === 'user'
                ? 'bg-[#f4d35e] text-black self-end rounded-br-none ml-auto'
                : 'bg-[#396041]/40 text-black self-start rounded-bl-none mr-auto'
            }`}
          >
            {msg.content}
            <span className="absolute -bottom-4 left-2 text-[10px] text-black/30 opacity-0 group-hover:opacity-100 transition">
              {msg.role === 'user' ? 'You' : 'Ecodia'}
            </span>
          </motion.div>
        ))}
        {loading && <div className="text-[#f4d35e] italic animate-pulse text-sm">Ecodia is thinking...</div>}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={e => {
          e.preventDefault()
          sendMessage()
        }}
        className="w-full max-w-3xl z-10 p-4 rounded-t-2xl border-t border-white/10 bg-[#0b0b0b]/80 backdrop-blur-md shadow-[0_-8px_40px_rgba(255,240,200,0.05)] ring-1 ring-white/5"
      >
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Speak to Ecodia..."
          className="w-full px-4 py-3 rounded-2xl bg-white/10 text-black placeholder-white/30 shadow-inner backdrop-blur-sm focus:outline-none focus:ring-2 focus:ring-[#f4d35e]/80 focus:ring-offset-1 focus:ring-offset-[#0b0b0b]"
        />
      </form>

      {error && <div className="text-red-500 text-sm text-center p-2 z-10">{error}</div>}
    </div>
  )
}

function AnimatedBackground({
  fireflyColor,
  shadowColor,
  motionIntensity
}: {
  fireflyColor: string
  shadowColor: string
  motionIntensity: number
}) {
  const fireflies = useMemo(() => Array.from({ length: 70 }, () => {
    const depth = Math.random()
    const depthFactor = 1 - depth
    const direction = Math.random() < 0.5 ? -1 : 1
    const size = depth < 0.1 ? Math.random() * 8 + 14 : depth < 0.4 ? Math.random() * 5 + 8 : depth < 0.7 ? Math.random() * 4 + 4 : Math.random() * 3 + 2
    const blur = depth < 0.1 ? 0 : depth < 0.4 ? 2 : depth < 0.7 ? 4 : 8
    const rawOpacity = depth < 0.1 ? 0.95 : depth < 0.4 ? 0.6 : depth < 0.7 ? 0.4 : 0.2
    const opacity = Math.max(rawOpacity, 0.2)
    const z = depth < 0.1 ? 50 : depth < 0.4 ? 30 : depth < 0.7 ? 20 : 10
    const pulseRange = 0.05 + depthFactor * 0.15
    const scaleCycle = [1, 1 + pulseRange * motionIntensity, 1]
    const opacityCycle = [opacity * 0.9, opacity, opacity * 0.9]
    return {
      x: Math.random() * 100,
      y: Math.random() * 100,
      size,
      blur,
      opacity,
      z,
      speed: 8 + Math.random() * 6 * depthFactor * motionIntensity,
      delay: Math.random() * 5,
      xDrift: motionIntensity * 50 * (Math.random() < 0.5 ? -1 : 1),
      yDrift: motionIntensity * 50 * direction,
      scaleCycle,
      opacityCycle,
    }
  }), [fireflyColor, shadowColor, motionIntensity])

  return (
    <div className="absolute inset-0 z-0 pointer-events-none overflow-hidden">
      {fireflies.map((f, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full"
          style={{
            left: `${f.x}%`,
            top: `${f.y}%`,
            width: `${f.size}px`,
            height: `${f.size}px`,
            background: `radial-gradient(circle, #ffffff 0%, ${fireflyColor} 40%, ${shadowColor} 100%)`,
            filter: `blur(${f.blur}px)`,
            opacity: f.opacity,
            boxShadow: f.blur === 0
              ? `0 0 ${f.size}px ${shadowColor}`
              : `0 0 ${f.size * 2}px ${shadowColor}`,
            zIndex: f.z,
          }}
          animate={{
            x: [0, f.xDrift, 0],
            y: [0, f.yDrift, 0],
            scale: f.scaleCycle,
            opacity: f.opacityCycle,
          }}
          transition={{
            duration: f.speed,
            repeat: Infinity,
            ease: 'easeInOut',
            delay: f.delay,
          }}
        />
      ))}
    </div>
  )
}
