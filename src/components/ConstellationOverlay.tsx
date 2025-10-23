// src/components/account/ConstellationIntro.tsx
'use client';

import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';

const CONSENT_KEY = 'constellationIntroAccepted:v3';
const MIN_DWELL_MS = 250;

export default function ConstellationIntro() {
  const [shownAt] = useState(() => Date.now());
  const [ready, setReady] = useState(false);
  const [accepted, setAccepted] = useState<boolean>(() => {
    try { return localStorage.getItem(CONSENT_KEY) === 'true'; } catch { return false; }
  });

  // Fake canvas ready (or wire to your real ready event)
  useEffect(() => {
    const t1 = setTimeout(() => setReady(true), 600);
    return () => clearTimeout(t1);
  }, []);

  if (accepted) return null;

  const allowDismiss = ready && Date.now() - shownAt >= MIN_DWELL_MS;

  const handleAccept = () => {
    if (!allowDismiss) return;
    try { localStorage.setItem(CONSENT_KEY, 'true'); } catch {}
    setAccepted(true);
  };

  return (
    <div className="fixed inset-0 z-50 ecodia-modal-backdrop">
      <div className="ecodia-modal" role="dialog" aria-modal="true" aria-labelledby="constellation-title">
        <button
          className="ecodia-modal__close"
          aria-label="Close"
          title={!allowDismiss ? 'Preparing…' : 'Close'}
          onClick={handleAccept}
          disabled={!allowDismiss}
        >
          ×
        </button>

        <h2 id="constellation-title" className="ecodia-modal__title">✨ Create Your Constellation</h2>

        <p className="ecodia-modal__body">
          Explore the canvas, pick your favorite stars, and jump in. This is just an intro — your account uses normal sign-in.
        </p>

        <motion.button
          onClick={handleAccept}
          disabled={!allowDismiss}
          className="ecodia-modal__cta"
          whileTap={{ scale: allowDismiss ? 0.98 : 1 }}
        >
          {!allowDismiss ? 'Preparing…' : 'Let’s go'}
        </motion.button>
      </div>
    </div>
  );
}
