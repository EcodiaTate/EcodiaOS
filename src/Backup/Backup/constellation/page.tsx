'use client'

import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import StarCanvas from '@/components/StarCanvas'

export default function ConstellationPage() {
  const router = useRouter()

  function handleComplete(selectedWords: string[]) {
    console.log('🪐 Soul Soul:', selectedWords)
    localStorage.setItem('soulNode', JSON.stringify(selectedWords))
    router.push('/soul')
  }

  return (
    <div className="w-full h-screen bg-black">
      <StarCanvas onComplete={handleComplete} />
    </div>
  )
}
