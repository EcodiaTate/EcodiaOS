'use client'

import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import Link from 'next/link'

export default function SoulPage() {
  const [words, setWords] = useState<string[]>([])
  const [soulNode, setSoulNode] = useState<string | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem('soulNode')
    if (stored) {
      const parsed = JSON.parse(stored)
      setWords(parsed)

      // 🌐 Call backend to generate soul soul
      fetch('http://localhost:8000/voxis/generate_soul', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ words: parsed }),
      })
        .then((res) => res.json())
        .then((data) => setSoulNode(data.soul))
        .catch((err) => console.error('Soul generation failed:', err))
    }
  }, [])

  return (
    <div className="min-h-screen bg-black text-black flex flex-col justify-center items-center px-6 py-10">
      <h1 className="text-3xl md:text-4xl font-bold tracking-widest mb-8 text-center text-yellow-100">
        Your Soul Soul
      </h1>

      {/* 🌟 Display Selected Words */}
      <div className="flex flex-wrap justify-center gap-4 max-w-3xl text-center">
        {words.map((word, i) => (
          <motion.div
            key={i}
            className="text-xl md:text-2xl font-mono px-4 py-2 rounded-lg bg-white/10 border border-white/20 shadow-md"
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.15, duration: 0.5 }}
          >
            {word}
          </motion.div>
        ))}
      </div>

      {/* 💭 Generation Notice + Spinner */}
      {!soulNode && (
        <motion.div
          className="mt-12 text-center text-yellow-100 text-lg md:text-xl max-w-xl italic flex flex-col items-center gap-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: words.length * 0.15 + 0.5 }}
        >
          forging your soul...
          <span className="text-sm opacity-80">be still, and remember it when it arrives.</span>
          <LoadingSpinner />
        </motion.div>
      )}

      {/* 💫 Display Generated Soul */}
      {soulNode && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: words.length * 0.15 + 1 }}
          className="mt-12 text-center text-yellow-100 text-2xl md:text-3xl font-semibold max-w-2xl"
        >
          {soulNode}
        </motion.div>
      )}

      {/* 🔁 Return Button */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: words.length * 0.15 + 1.5 }}
        className="mt-10"
      >
        <Link href="/">
          <button className="px-6 py-3 bg-white text-black rounded-lg shadow hover:bg-yellow-100 transition">
            Return Home
          </button>
        </Link>
      </motion.div>
    </div>
  )
}

function LoadingSpinner() {
  return (
    <div className="w-8 h-8 border-4 border-yellow-100 border-t-transparent rounded-full animate-spin" />
  )
}
