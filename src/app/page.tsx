'use client'

import { useEffect } from 'react'
import dynamic from 'next/dynamic'
import { useSearchParams } from 'next/navigation'
import { useModeStore } from '@/stores/useModeStore'
import EcodiaOverlay from '@/components/EcodiaOverlay'

const EcodiaStarCanvas = dynamic(() => import('@/components/EcodiaStarCanvas'), { ssr: false })

export default function Page() {
  const searchParams = useSearchParams()
  const setMode = useModeStore((s) => s.setMode)

  useEffect(() => {
    const urlMode = searchParams.get('mode') || 'boot'
    setMode(urlMode as any)
  }, [searchParams, setMode])

  return (
    <main className="fixed inset-0 w-dvw h-dvh bg-black overflow-hidden">
      <EcodiaStarCanvas />
      <EcodiaOverlay />
    </main>
  )
}
