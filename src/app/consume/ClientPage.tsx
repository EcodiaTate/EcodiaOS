// src/app/link/consume/page.tsx
'use client'
import { useEffect, useState } from 'react'
import { useSearchParams, useRouter } from 'next/navigation'
import { consumeLink } from '@/lib/api/linking'

export default function LinkConsumePage() {
  const params = useSearchParams()
  const router = useRouter()
  const token = params.get('token') || ''
  const [status, setStatus] = useState<'idle'|'ok'|'err'>('idle')
  const [msg, setMsg] = useState('Linking your accounts…')

  useEffect(() => {
    (async () => {
      if (!token) { setStatus('err'); setMsg('Missing token.'); return }
      try {
        await consumeLink({ token })
        setStatus('ok')
        setMsg('Linked! Redirecting…')
        setTimeout(() => router.push('/'), 900)
      } catch (e: any) {
        setStatus('err')
        setMsg(e?.message || 'Link failed. Try starting from the other site.')
      }
    })()
  }, [token, router])

  return (
    <div className="min-h-[60vh] grid place-items-center text-center p-6">
      <div className="rounded-2xl px-6 py-5 bg-white/5 text-white ring-1 ring-white/15">
        <h1 className="text-xl font-semibold mb-2">Account Linking</h1>
        <p className={status==='err' ? 'text-red-300' : 'text-white/80'}>{msg}</p>
      </div>
    </div>
  )
}
