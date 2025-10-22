'use client'

import React from 'react'
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
}

const formatProperty = (prop: string): string => {
  return prop
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, (str) => str.toUpperCase())
    .trim()
}

export const ConsentToast: React.FC<ConsentToastProps> = ({ isVisible, upsert, onAccept, onDecline }) => {
  if (!upsert) return null

  const displayProperty = formatProperty(upsert.property)
  const displayValue = String(upsert.value)

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0, y: 50, scale: 0.9 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 20, scale: 0.95 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          // 👇 POSITIONING & SIZING CLASSES CHANGED HERE
          className="fixed bottom-24 left-4 w-full max-w-sm p-3 rounded-xl shadow-2xl bg-[#0b0b0b]/80 backdrop-blur-lg border border-white/10 z-50 pointer-events-auto"
        >
          <div className="text-center">
            {/* 👇 FONT SIZE REDUCED */}
            <p className="text-xs text-white/80">Remember this?</p>
            <p className="text-base font-medium text-[#F4D35E] my-1">
              <span className="text-white/90">{displayProperty}:</span> {`"${displayValue}"`}
            </p>
          </div>
          <div className="flex justify-center gap-3 mt-3">
            {/* 👇 BUTTON & ICON SIZE REDUCED */}
            <button
              onClick={() => onDecline(upsert)}
              className="flex items-center justify-center w-12 h-12 bg-red-900/40 text-red-300 rounded-full border border-red-500/50 hover:bg-red-900/70 transition-colors duration-200"
              aria-label="Decline"
            >
              <X size={24} />
            </button>
            <button
              onClick={() => onAccept(upsert)}
              className="flex items-center justify-center w-12 h-12 bg-green-900/40 text-green-300 rounded-full border border-green-500/50 hover:bg-green-900/70 transition-colors duration-200"
              aria-label="Accept"
            >
              <Check size={24} />
            </button>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}