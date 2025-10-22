'use client'
import React, { useState } from 'react'
import { Volume2, Copy as CopyIcon } from 'lucide-react'
import { stripTags } from './utils'

export function MessageActions({
  text,
  onSpeak,
}: {
  text: string
  onSpeak: (t: string) => Promise<void> | void
}) {
  const [busy, setBusy] = useState(false)

  const onCopy = async () => {
    try { await navigator.clipboard.writeText(stripTags(text)) } catch {}
  }

  const speak = async () => {
    if (busy) return
    setBusy(true)
    try { await onSpeak(text) } finally { setBusy(false) }
  }

  return (
    <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-white/60">
      <button type="button" onClick={onCopy}
        className="px-2 py-1 rounded-md bg-white/5 hover:bg-white/10 transition"
        title="Copy" aria-label="Copy message">
        <CopyIcon size={14} />
      </button>
      <button type="button" onClick={speak}
        className="px-2 py-1 rounded-md bg-white/5 hover:bg-white/10 transition disabled:opacity-50"
        title="Say this" aria-label="Say this" disabled={busy}>
        <Volume2 size={14} />
      </button>
    </div>
  )
}
