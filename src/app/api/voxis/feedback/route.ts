// src/app/api/voxis/feedback/route.ts
import { NextRequest, NextResponse } from 'next/server'

export const runtime = 'nodejs'
export const dynamic = 'force-dynamic'

const API_BASE = (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8080').replace(/\/+$/, '')
const BACKEND_PATH = '/voxis/feedback'
const TIMEOUT_MS = 15000

export async function POST(req: NextRequest) {
  if (!API_BASE) {
    return NextResponse.json({ ok: false, error: 'BACKEND URL not configured' }, { status: 500 })
  }

  let body: any
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid JSON' }, { status: 400 })
  }

  // Accept legacy chosen_arm_id or new arm_id; prefer arm_id if present
  const arm_id = (body?.arm_id ?? body?.chosen_arm_id)?.toString()
  const episode_id = body?.episode_id?.toString()
  const utility = typeof body?.utility === 'number' ? body.utility : NaN

  if (!episode_id || !arm_id || Number.isNaN(utility)) {
    return NextResponse.json(
      { ok: false, error: 'Missing episode_id, arm_id/chosen_arm_id, or utility' },
      { status: 422 }
    )
  }
  if (utility < 0 || utility > 1) {
    return NextResponse.json(
      { ok: false, error: 'utility must be between 0 and 1' },
      { status: 422 }
    )
  }

  const idempotencyKey =
    (body?.idempotency_key && String(body.idempotency_key)) ||
    req.headers.get('Idempotency-Key') ||
    undefined

  const ctrl = new AbortController()
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS)

  try {
    const res = await fetch(API_BASE + BACKEND_PATH, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
      },
      body: JSON.stringify({
        episode_id,
        // Keep legacy compatibility but normalize on the backend:
        chosen_arm_id: arm_id,
        arm_id, // new preferred field
        utility,
        // Optional passthrough for analytics/debug
        meta: body?.meta ?? null,
      }),
      cache: 'no-store',
      signal: ctrl.signal,
    })

    const text = await res.text()
    let data: any
    try { data = JSON.parse(text) } catch { data = { passthrough: text } }

    return NextResponse.json({ ok: res.ok, status: res.status, data }, { status: res.ok ? 200 : res.status })
  } catch (e: any) {
    const msg = e?.name === 'AbortError' ? 'Upstream timeout' : (e?.message || 'Server error')
    return NextResponse.json({ ok: false, error: msg }, { status: 500 })
  } finally {
    clearTimeout(t)
  }
}
