// src/components/VoiceFlowController.tsx
'use client';

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { useVoiceStore } from '@/stores/useVoiceStore';

type Target = { uniforms?: Record<string, { value: any }> };
// Pass refs to materials that should respond (e.g., canopy line material, particle mat)
export default function VoiceFlowController({
  targets,
  theme = 0.4,
}: {
  targets: Array<React.MutableRefObject<Target | null>>;
  theme?: number;
}) {
  const lastBurst = useRef(-1);
  const isPlaying = useVoiceStore(s => s.isPlaying);

  useFrame(({ clock }) => {
    const now = clock.elapsedTime * 1000;
    const talking = isPlaying ? 1 : 0;

    // gentle periodic ripple when talking
    if (talking && (lastBurst.current < 0 || now - lastBurst.current > 1600)) {
      lastBurst.current = now;
      for (const r of targets) {
        const t = r.current;
        if (!t?.uniforms) continue;
        t.uniforms.uActivatedAt && (t.uniforms.uActivatedAt.value = now);
        t.uniforms.uDuration && (t.uniforms.uDuration.value = 2200);
      }
    }

    for (const r of targets) {
      const t = r.current;
      if (!t?.uniforms) continue;
      t.uniforms.uTime && (t.uniforms.uTime.value = now);
      t.uniforms.uTheme && (t.uniforms.uTheme.value = theme);
    }
  });

  return null;
}
