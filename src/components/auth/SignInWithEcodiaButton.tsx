// SignInWithEcodiaButton.tsx
'use client';
const ECODIA_URL = process.env.NEXT_PUBLIC_ECODIA_URL || 'http://localhost:3001';
export function SignInWithEcodiaButton() {
  const redirect = '/auth/after-ecodia?mode=hub';
  return (
    <a href={`${ECODIA_URL}/api/sso/issue?redirect=${encodeURIComponent(redirect)}`} className="ec-btn">
      Sign in with Ecodia
    </a>
  );
}
