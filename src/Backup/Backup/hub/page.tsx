// app/hub/page.tsx
'use client'

import dynamic from 'next/dynamic'
import { Suspense } from 'react'

const EcodiaMind = dynamic(() => import('@/components/EcodiaMind'), { ssr: false })

export default function Page() {
  return (
    <main className="fixed inset-0 w-screen h-screen m-0 p-0 overflow-hidden bg-black">
      <Suspense fallback={<div className="text-black">Loading cognition...</div>}>
        <EcodiaMind />
      </Suspense>
    </main>
  )
}
