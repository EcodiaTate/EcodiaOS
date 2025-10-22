'use client'
import React from 'react'

export function VoiceHUD({ active }: { active: boolean }) {
  return (
    <div
      aria-hidden
      className={`relative w-6 h-6 rounded-full ${active ? 'bg-emerald-400/30' : 'bg-white/10'}`}
      title={active ? 'Voice active' : 'Voice idle'}
    >
      <div className={`absolute inset-0 rounded-full ${active ? 'animate-ping bg-emerald-400/40' : ''}`} />
      <div className={`absolute inset-1 rounded-full ${active ? 'bg-emerald-400' : 'bg-white/30'}`} />
    </div>
  )
}
