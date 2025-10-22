// src/components/PostFX.tsx
'use client';

import React from 'react';
import { EffectComposer, Bloom, Vignette, BrightnessContrast } from '@react-three/postprocessing';

export default function PostFX() {
  return (
    <EffectComposer multisampling={0}> 
      {/* soft bloom; keep threshold high so only glows pop */}
      <Bloom intensity={0.35} luminanceThreshold={0.85} luminanceSmoothing={0.2} mipmapBlur />
      {/* gentle global balance — premium feel, no washout */}
      <BrightnessContrast brightness={0.02} contrast={0.06} />
      <Vignette eskil={false} offset={0.2} darkness={0.25} />
    </EffectComposer>
  );
}
