'use client'

import React from 'react'
import { useModeStore } from '@/stores/useModeStore'
import { BackToRootButton, BackToEcodiaButton, ContactEcodiaButton } from '@/components/ui'

export default function HubOverlay() {
  const setMode = useModeStore((s) => s.setMode)

  return (
    <div className="hubo">
      {/* Hub Panel */}
      <section aria-label="Ecodia Hub Overlay" className="hubo-wrap">
        <div className="hubo-panel" role="dialog" aria-modal="true">
          <h1 className="hubo-title">Explore</h1>

          <div className="hubo-actions" role="group" aria-label="Primary actions">
            <button
              className="hubo-btn"
              onClick={() => setMode('talk')}
              aria-label="Talk to Ecodia"
            >
              Talk to Ecodia
            </button>

            <button
              className="hubo-btn hubo-btn--secondary"
              onClick={() => setMode('guide')}
              aria-label="Guide Ecodia"
            >
              Guide Ecodia
            </button>
          </div>
        </div>
      </section>

      {/* Floating controls (top-right, always clickable) */}
<div className="hub-controls pointer-events-auto">
  <BackToRootButton />
  <ContactEcodiaButton />
  <BackToEcodiaButton />
</div>


    </div>
  )
}
