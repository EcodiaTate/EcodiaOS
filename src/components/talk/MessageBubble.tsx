'use client'
import React from 'react'
import { motion } from 'framer-motion'
import { AudioLines } from 'lucide-react'
import { MarkdownBubble } from './MarkdownBubble'
import type { Message } from './types'

export function MessageBubble({
  msg,
  isUser,
  children, // actions / feedback
}: {
  msg: Message
  isUser: boolean
  children?: React.ReactNode
}) {
  const bubbleClass = [
    'w-fit max-w-[80%] whitespace-pre-wrap break-words rounded-2xl px-4 py-2 text-sm leading-5 shadow-sm',
    isUser ? 'bg-[#F4D35E] text-black self-end rounded-br-none' : 'bg-[#396041] text-white self-start rounded-bl-none',
    msg.emotionClass ?? '',
  ].join(' ')

  const displayContent = msg.content?.trim().length ? msg.content : '…'

  return (
    <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={bubbleClass}>
        {msg.ttsPending ? (
          <div className="relative flex items-center justify-center w-10 h-10">
            <span className="sr-only">Preparing audio…</span>
            <span className="absolute inset-0 rounded-full bg-white/10 animate-ping" />
            <div className="relative z-10 flex items-center justify-center w-9 h-9 rounded-full bg-white/15">
              <AudioLines className="opacity-90" size={18} />
            </div>
          </div>
        ) : (
          <MarkdownBubble text={displayContent} />
        )}
      </motion.div>

      {children}
    </div>
  )
}
