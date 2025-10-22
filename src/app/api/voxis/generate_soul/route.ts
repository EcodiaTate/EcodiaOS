// src/app/api/voxis/generate-soul/route.ts

import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

const API_BASE = (process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000').replace(/\/+$/, '');
const BACKEND_PATH = '/voxis/generate_soul';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    if (!body.words || !Array.isArray(body.words) || body.words.length === 0) {
      return NextResponse.json({ error: 'Words array is required' }, { status: 400 });
    }

    const backendUrl = API_BASE + BACKEND_PATH;

    const upstreamResponse = await fetch(backendUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      cache: 'no-store',
    });

    const data = await upstreamResponse.json();

    if (!upstreamResponse.ok) {
      return NextResponse.json({ error: data.detail || 'Backend error during soul generation' }, { status: upstreamResponse.status });
    }

    return NextResponse.json(data, { status: 200 });

  } catch (e: any) {
    console.error('[API Proxy /generate_soul] Error:', e);
    return NextResponse.json({ error: e?.message || 'Server error' }, { status: 500 });
  }
}