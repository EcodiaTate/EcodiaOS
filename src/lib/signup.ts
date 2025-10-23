// src/lib/signup.ts
export async function signUpThenSignIn(email: string, password: string) {
  const base = (process.env.NEXT_PUBLIC_API_URL || '').replace(/\/+$/, '')
  const r = await fetch(`${base}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
    body: JSON.stringify({ email, password }),
  })
  if (!r.ok) {
    let msg = ''
    try { const j = await r.json(); msg = j.error || j.detail || JSON.stringify(j) } catch {}
    throw new Error(msg || `Register failed: ${r.status}`)
  }
  // then in the overlay: await signIn('credentials', { email, password, redirect: false })
}
