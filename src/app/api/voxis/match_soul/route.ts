// src/app/api/voxis/match_soul/route.ts
import { NextRequest, NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const API_BASE = (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '')
const BACKEND_PATH = '/voxis/match_soul'

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const soul = (body?.soul ?? '').trim()
    if (!soul) {
      return NextResponse.json({ error: 'No soul provided' }, { status: 400 })
    }

    const upstream = await fetch(API_BASE + BACKEND_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ soul }),
      cache: 'no-store',
    })

    const data = await upstream.json()

    if (!upstream.ok) {
      return NextResponse.json({ error: data.error || 'Match failed' }, { status: upstream.status })
    }

    // Normalize id
    const uuid = data.uuid || data.key_id || data.event_id || null
    return NextResponse.json({ ...data, uuid }, { status: 200 })
  } catch (e: any) {
    console.error('[API Proxy /match_soul] Error:', e)
    return NextResponse.json({ error: e?.message || 'Server error' }, { status: 500 })
  }
}
