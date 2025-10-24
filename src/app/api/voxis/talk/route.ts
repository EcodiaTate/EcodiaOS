// src/app/api/alive/talk/route.ts
import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const API_BASE = (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8080').replace(/\/+$/, '');
const BACKEND_PATH = '/alive/talk';
const TIMEOUT_MS = 20000;

function pickResultId(req: NextRequest, params?: { slug?: string[] }) {
  const qp = new URL(req.url).searchParams.get('result_id');
  if (qp) return qp;
  const fromSlug = params?.slug?.at(-1);
  if (fromSlug) return fromSlug;
  return null;
}

function upstreamContentType(res: Response) {
  return res.headers.get('content-type') ?? 'application/json; charset=utf-8';
}

async function readUpstream(res: Response) {
  const ct = upstreamContentType(res).toLowerCase();
  const text = await res.text();
  if (ct.includes('application/json')) {
    try { return { body: JSON.parse(text), contentType: ct, isJson: true }; } catch {}
  }
  return { body: text, contentType: ct, isJson: false };
}

export async function POST(req: NextRequest) {
  let payload: any;
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
  }

  // HARD REQUIREMENTS: must have user_id and soul_event_id
  if (!payload?.user_input || !payload?.soul_event_id) {
    return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
  }
  if (!payload?.user_id || payload.user_id === 'user_anon') {
    return NextResponse.json({ error: 'Missing user identity' }, { status: 401 });
  }

  try {
    const backendUrl = API_BASE + BACKEND_PATH;
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);

    // Pass-through; DO NOT override user_id
    const upstream = await fetch(backendUrl, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: JSON.stringify(payload),
      cache: 'no-store',
      signal: ctrl.signal,
    }).finally(() => clearTimeout(t));

    const { body: data, contentType, isJson } = await readUpstream(upstream);

    if (!upstream.ok) {
      const message = (isJson && (data as any)?.error) || 'Backend error';
      return NextResponse.json({ error: message }, { status: upstream.status });
    }

    return isJson
      ? NextResponse.json(data, { status: upstream.status })
      : new NextResponse(String(data), { status: upstream.status, headers: { 'content-type': contentType } });
  } catch (e: any) {
    const msg = e?.name === 'AbortError' ? 'Upstream timeout' : (e?.message || 'Server error');
    console.error('[API Proxy POST /alive/talk] Error:', e);
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}

export async function GET(req: NextRequest, ctx?: { params?: { slug?: string[] } }) {
  try {
    const resultId = pickResultId(req, ctx?.params);
    if (!resultId) {
      return NextResponse.json({ error: 'Missing result_id for polling' }, { status: 400 });
    }
    const backendUrl = `${API_BASE}${BACKEND_PATH}/result/${encodeURIComponent(resultId)}`;

    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);

    const upstream = await fetch(backendUrl, {
      method: 'GET',
      headers: { accept: 'application/json' },
      cache: 'no-store',
      signal: ctrl.signal,
    }).finally(() => clearTimeout(t));

    const { body: data, contentType, isJson } = await readUpstream(upstream);

    if (!upstream.ok) {
      const message = (isJson && (data as any)?.error) || 'Polling failed';
      return NextResponse.json({ error: message }, { status: upstream.status });
    }

    return isJson
      ? NextResponse.json(data, { status: upstream.status })
      : new NextResponse(String(data), { status: upstream.status, headers: { 'content-type': contentType } });
  } catch (e: any) {
    const msg = e?.name === 'AbortError' ? 'Upstream timeout' : (e?.message || 'Server error');
    console.error('[API Proxy GET /alive/talk] Error:', e);
    return NextResponse.json({ error: msg }, { status: 502 });
  }
}
