import { NextRequest, NextResponse } from 'next/server'
export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const API_BASE = (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '')
const BACKEND_PATH = '/voxis/talk/history'
const TIMEOUT_MS = 15000

export async function GET(req: NextRequest) {
  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS)
  try {
    const url = new URL(req.url)
    const qs = url.search ? url.search : ''
    const upstream = await fetch(API_BASE + BACKEND_PATH + qs, {
      method: 'GET',
      headers: { accept: 'application/json' },
      cache: 'no-store',
      signal: ctrl.signal,
    }).finally(() => clearTimeout(t))

    const text = await upstream.text()
    let data: any
    try { data = JSON.parse(text) } catch { data = text }

    return upstream.ok
      ? NextResponse.json(data, { status: 200 })
      : NextResponse.json({ error: data?.error || 'History fetch failed' }, { status: upstream.status })
  } catch (e: any) {
    const msg = e?.name === 'AbortError' ? 'Upstream timeout' : (e?.message || 'Server error')
    return NextResponse.json({ error: msg }, { status: 502 })
  } finally {
    clearTimeout(t)
  }
}
