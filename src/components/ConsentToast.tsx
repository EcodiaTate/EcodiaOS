'use client'

import React, { useEffect, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Check, X } from 'lucide-react'

export type ProfileUpsert = {
  property: string
  value: string | number | boolean
  raw_data: any
}

interface ConsentToastProps {
  isVisible: boolean
  upsert: ProfileUpsert | null
  onAccept: (upsert: ProfileUpsert) => void
  onDecline: (upsert: ProfileUpsert) => void
  /** Optional: where to dock the toast */
  position?: 'bl' | 'br' | 'bc' // bottom-left / bottom-right / bottom-center
}

const formatProperty = (prop: string): string =>
  prop
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (s) => s.toUpperCase())
    .trim()

/** subtle pointer parallax + shine */
function useToastParallax() {
  const ref = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const onMove = (e: MouseEvent) => {
      const r = el.getBoundingClientRect()
      const x = (e.clientX - r.left) / r.width - 0.5
      const y = (e.clientY - r.top) / r.height - 0.5
      el.style.setProperty('--tiltX', `${-(y * 1.2)}deg`)
      el.style.setProperty('--tiltY', `${x * 1.2}deg`)
      el.style.setProperty('--shineX', `${e.clientX - r.left}px`)
      el.style.setProperty('--shineY', `${e.clientY - r.top}px`)
    }
    window.addEventListener('mousemove', onMove)
    return () => window.removeEventListener('mousemove', onMove)
  }, [])
  return ref
}

export const ConsentToast: React.FC<ConsentToastProps> = ({
  isVisible,
  upsert,
  onAccept,
  onDecline,
  position = 'bl',
}) => {
  if (!upsert) return null

  const displayProperty = formatProperty(upsert.property)
  const displayValue = String(upsert.value)
  const ref = useToastParallax()

  const posClass =
    position === 'br'
      ? 'right-4 bottom-6 sm:bottom-8'
      : position === 'bc'
      ? 'left-1/2 -translate-x-1/2 bottom-6 sm:bottom-8'
      : 'left-4 bottom-6 sm:bottom-8' // 'bl' default

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          ref={ref}
          initial={{ opacity: 0, y: 28, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 16, scale: 0.98 }}
          transition={{ duration: 0.28, ease: 'easeOut' }}
          className={`fixed z-9997 ${posClass} pointer-events-auto`}
        >
          <div className="ec-toast">
            {/* energy seam */}
            <div className="ec-toast__border" aria-hidden="true" />
            {/* pointer-follow shine */}
            <div className="ec-toast__shine" aria-hidden="true" />

            <div className="ec-toast__body">
              <p className="ec-toast__eyebrow">Remember this?</p>
              <p className="ec-toast__line">
                <span className="ec-toast__label">{displayProperty}:</span>{' '}
                <span className="ec-toast__value">“{displayValue}”</span>
              </p>

              <div className="ec-toast__actions" role="group" aria-label="Consent actions">
                <button
                  onClick={() => onDecline(upsert)}
                  className="ec-toast__btn ec-toast__btn--decline"
                  aria-label="Decline"
                >
                  <X size={18} aria-hidden />
                </button>

                <button
                  onClick={() => onAccept(upsert)}
                  className="ec-toast__btn ec-toast__btn--accept"
                  aria-label="Accept"
                  autoFocus
                >
                  <Check size={18} aria-hidden />
                </button>
              </div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
