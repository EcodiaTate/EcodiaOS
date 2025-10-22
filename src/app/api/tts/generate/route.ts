// src/app/api/tts/generate/route.ts
import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const API_BASE = (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8080').replace(/\/+$/, '');
const BACKEND_PATH = '/voxis/tts/synthesize';
const TIMEOUT_MS = 20000;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    if (!body?.text) {
      return NextResponse.json({ error: 'Text is required for TTS' }, { status: 400 });
    }

    const backendUrl = API_BASE + BACKEND_PATH;

    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);

    const upstreamResponse = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      cache: 'no-store',
      signal: ctrl.signal,
    }).finally(() => clearTimeout(t));

    if (!upstreamResponse.ok) {
      // try to read json, otherwise text
      let errPayload: any;
      try { errPayload = await upstreamResponse.json(); }
      catch { errPayload = { detail: await upstreamResponse.text() }; }
      return NextResponse.json(
        { error: errPayload?.detail || 'TTS generation failed', data: errPayload },
        { status: upstreamResponse.status },
      );
    }

    const buf = Buffer.from(await upstreamResponse.arrayBuffer());
    const ct = upstreamResponse.headers.get('Content-Type') || 'audio/mpeg';

    return new NextResponse(buf, {
      status: 200,
      headers: {
        'Content-Type': ct,
        'Content-Length': String(buf.length),
        // Let the browser cache aggressively for the session if you want:
        // 'Cache-Control': 'no-store',
      },
    });
  } catch (e: any) {
    const msg = e?.name === 'AbortError' ? 'Upstream timeout' : (e?.message || 'Server error');
    console.error('[API Proxy /voxis/tts/synthesize] Error:', e);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
