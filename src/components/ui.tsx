'use client'

import { useModeStore } from '@/stores/useModeStore'
import { ECODIA_URL } from '@/lib/env';

interface Props {
  className?: string
}

/* Shared Ecodia button styles */
const ecGrad =
  'bg-[radial-gradient(120%_140%_at_15%_15%,rgba(255,255,255,.12)_0%,transparent_55%),linear-gradient(135deg,#396041_0%,#7FD069_60%,#F4D35E_100%)]'
const ecGlass =
  'bg-[linear-gradient(180deg,rgba(255,255,255,.08),rgba(255,255,255,.04))]'

const ecBtnBase =
  'inline-flex items-center justify-center rounded-full text-white font-semibold ' +
  'border border-black/40 shadow-[0_10px_28px_rgba(0,0,0,.45)] ' +
  'ring-1 ring-white/10 backdrop-blur-md ' +
  'transition will-change-transform hover:scale-[1.02] ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-black ' +
  'focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a0f0c]'

const ecBtnSecondaryBase =
  'inline-flex items-center justify-center rounded-full text-[rgba(233,244,236,.95)] ' +
  'border border-white/20 shadow-[0_10px_28px_rgba(0,0,0,.45)] ' +
  'ring-1 ring-white/10 backdrop-blur-md ' +
  'transition will-change-transform hover:scale-[1.02] ' +
  'focus:outline-none focus-visible:ring-2 focus-visible:ring-black ' +
  'focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a0f0c]'

/* ← Back to Hub (top-left) */
export function BackToHubButton({ className = '' }: Props) {
  const setMode = useModeStore((s) => s.setMode)
  return (
    <button
      onClick={() => setMode('hub')}
      aria-label="Back to Hub"
      title="Back to Hub"
      className={`absolute top-4 left-4 z-20 h-9 min-w-2.25rem px-3 text-sm ${ecBtnBase} ${ecGrad} ${className}`}
    >
      ←
    </button>
  )
}

/* ← Back to Root (top-left) */
export function BackToRootButton({ className = '' }: Props) {
  const setMode = useModeStore((s) => s.setMode)
  return (
    <button
      onClick={() => setMode('root')}
      aria-label="Back to Home"
      title="Back to Home"
      className={`absolute top-4 left-4 z-20 h-9 min-w-2.25rem px-3 text-sm ${ecBtnBase} ${ecGrad} ${className}`}
    >
      ←
    </button>
  )
}

/* ✉ Contact Ecodia (bottom-right) */
export function ContactEcodiaButton({ className = '' }: Props) {
  return (
    <a
      href="mailto:connect@ecodia.au?subject=Account%20Support%20or%20Data%20Deletion%20Request"
      aria-label="Contact Ecodia Support"
      title="Contact Ecodia Support"
      className={`absolute bottom-4 right-4 z-20 w-10 h-10 text-lg ${ecBtnSecondaryBase} ${ecGlass} hover:bg-white/20 ${className}`}
    >
      ✉
    </a>
  )
}

/* ⧉ Back to Ecodia (top-right) */
export function BackToEcodiaButton({ className = '' }: { className?: string }) {
  return (
    <div className={`absolute top-5 right-5 z-30 group ${className}`}>
      <button
        onClick={() => window.open('https://ecodia.au', '_blank')}
        aria-label="Open ecodia.au"
        title="Open ecodia.au"
        className="w-10 h-10 p-0 m-0 rounded-xl bg-transparent border-0 outline-none
                   pointer-events-auto transition-transform hover:scale-[1.03]
                   focus-visible:ring-2 focus-visible:ring-[#7FD069]/60"
      >
        <img
          src="/assets/button.png"
          alt="Ecodia"
          className="w-full h-full rounded-2rem object-contain"
        />
      </button>

      {/* Tooltip - below the button, slightly left so it stays in view */}
      <div
        className="absolute top-full mt-1 right-0 -translate-x-2 px-2 py-1 text-xs text-white
                   bg-black/80 rounded-md opacity-0 group-hover:opacity-100 transition
                   pointer-events-none whitespace-nowrap"
      >
        Back to Ecodia
      </div>
    </div>
  )
}




/* 🌗 Theme Toggle - dark-only app: keep export to avoid import errors (renders nothing) */
export function ThemeToggleButton(_props: Props) {
  return null
}
