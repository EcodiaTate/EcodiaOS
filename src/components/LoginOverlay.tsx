// src/components/LoginOverlay.tsx
'use client';

import React, { useMemo, useState } from 'react';
import { signIn } from 'next-auth/react';
import { useModeStore } from '@/stores/useModeStore';

type Props = {
  isOpen: boolean;
  onClose: () => void;
  enableGoogle?: boolean;
};

export default function LoginOverlay({
  isOpen,
  onClose,
  enableGoogle = true,
}: Props) {
  const setMode = useModeStore((s) => s.setMode);

  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  const hidden = useMemo(
    () => (!isOpen ? 'pointer-events-none opacity-0' : 'opacity-100'),
    [isOpen]
  );

  async function doCredentials(e: React.FormEvent) {
    e.preventDefault();
    setErr('');
    setBusy(true);
    try {
      const res = await signIn('credentials', {
        email,
        password: pw,
        redirect: false,
      });
      if (!res || (res as any).error) {
        throw new Error((res as any)?.error || 'Invalid email or password');
      }
      // ✅ success → switch mode
      setMode('hub');
    } catch (e: any) {
      setErr(e?.message || 'Login failed');
    } finally {
      setBusy(false);
    }
  }

  async function doGoogle() {
    setErr('');
    setBusy(true);
    // NextAuth will complete the flow and we flip mode on return
    await signIn('google', { redirect: false });
    setMode('hub');
  }

  return (
    <div
      className={`fixed inset-0 z-10000 transition ${hidden}`}
      aria-hidden={!isOpen}
      role="dialog"
      aria-modal="true"
      aria-label="Login"
    >
      <div className="absolute inset-0 bg-[#0b1310]/80" onClick={onClose} />

      <div className="absolute left-1/2 top-1/2 w-[min(520px,92vw)] -translate-x-1/2 -translate-y-1/2">
        <div className="relative rounded-2xl p-5 bg-[rgba(255,255,255,0.06)] shadow-[0_14px_40px_rgba(0,0,0,0.35)]">
          <div
            className="pointer-events-none absolute inset-0 rounded-2xl p-1
                        [background:linear-gradient(135deg,rgba(127,208,105,.8),rgba(244,211,94,.8))]
                        [-webkit-mask:linear-gradient(#000_0_0)_content-box,linear-gradient(#000_0_0)]
                        mask-composite:exclude [-webkit-mask-composite:xor]"
          />

          <header className="text-center">
            <h2 className="text-[22px] font-semibold tracking-wide text-white">Sign in</h2>
            <p className="mt-1 text-white/70 text-sm">
              Use your email/password or continue with Google.
            </p>
          </header>

          <form className="mt-5 space-y-3" onSubmit={doCredentials}>
            <div>
              <label htmlFor="email" className="sr-only">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                className="w-full rounded-xl bg-white/10 text-white px-3 py-2 ring-1 ring-white/20 focus:outline-none focus:ring-white/40"
                placeholder="you@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={busy}
                required
              />
            </div>

            <div>
              <label htmlFor="password" className="sr-only">Password</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className="w-full rounded-xl bg-white/10 text-white px-3 py-2 ring-1 ring-white/20 focus:outline-none focus:ring-white/40"
                placeholder="Password"
                value={pw}
                onChange={(e) => setPw(e.target.value)}
                disabled={busy}
                required
              />
            </div>

            {err && <p className="text-red-300 text-sm">{err}</p>}

            <button
              className="w-full rounded-xl px-4 py-2 font-semibold text-[#0b1310]
                         bg-white shadow-[0_10px_28px_rgba(127,208,105,0.35)]
                         ring-1 ring-[rgba(127,208,105,0.55)] hover:shadow-[0_12px_34px_rgba(127,208,105,0.45)]"
              type="submit"
              disabled={busy}
            >
              {busy ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          {enableGoogle && (
            <div className="mt-4">
              <button
                className="w-full rounded-xl px-4 py-2 font-semibold text-white/90 bg-white/10 ring-1 ring-white/20"
                onClick={doGoogle}
                disabled={busy}
              >
                Continue with Google
              </button>
            </div>
          )}

          <div className="mt-4 flex justify-center">
            <button
              className="rounded-xl px-4 py-2 font-semibold text-white/90 bg-white/10 ring-1 ring-white/20"
              onClick={onClose}
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
