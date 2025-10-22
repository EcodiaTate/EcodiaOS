'use client'
import React from 'react'
import { MessageSquareText, AudioLines } from 'lucide-react'

export function ModeSwitch({
  mode,
  onChange,
  disabled,
}: {
  mode: 'typing' | 'voice'
  onChange: (m: 'typing' | 'voice') => void
  disabled?: boolean
}) {
  const Item = ({
    value, label, icon,
  }: { value: 'typing' | 'voice'; label: string; icon: React.ReactNode }) => {
    const selected = mode === value
    return (
      <button
        type="button"
        onClick={() => onChange(value)}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition
          ${selected ? 'bg-white text-black' : 'text-white/70 hover:text-white'} disabled:opacity-50`}
        aria-pressed={selected}
        aria-label={`Switch to ${label} mode`}
        disabled={disabled}
      >
        {icon}
        <span className="hidden sm:inline">{label}</span>
      </button>
    )
  }

  return (
    <div role="tablist" aria-label="Output mode"
         className="inline-flex items-center gap-1 p-1 rounded-xl bg-white/10 backdrop-blur border border-white/10">
      <Item value="typing" label="Typing" icon={<MessageSquareText size={16} />} />
      <Item value="voice" label="Voice" icon={<AudioLines size={16} />} />
    </div>
  )
}
