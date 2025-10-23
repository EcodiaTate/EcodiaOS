'use client'

import { useEffect } from 'react'
import dynamic from 'next/dynamic'
import { useSearchParams } from 'next/navigation'
import { useModeStore } from '@/stores/useModeStore'
import EcodiaOverlay from '@/components/EcodiaOverlay'

const EcodiaCanvas = dynamic(() => import('@/components/EcodiaCanvas'), { ssr: false })

export default function Page() {
  const searchParams = useSearchParams()
  const setMode = useModeStore((s) => s.setMode)

  useEffect(() => {
    // --- THIS IS THE FIX ---
    // Only update the mode from the URL *if* the 'mode' param
    // is explicitly present.
    // Otherwise, we trust the mode that's already in the store
    // (which was set by the /auth/after-ecodia page).
    const urlMode = searchParams.get('mode');
    if (urlMode) {
      setMode(urlMode as any);
    }
    // If 'urlMode' is null, we do *nothing*, which
    // preserves the 'hub' mode.
    // --- END FIX ---
  }, [searchParams, setMode])

  return (
    <main className="fixed inset-0 w-dvw h-dvh bg-black overflow-hidden">
      <EcodiaCanvas />
      <EcodiaOverlay />
    </main>
  )
}
