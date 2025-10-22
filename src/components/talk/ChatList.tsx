'use client'

import React, { useEffect, useMemo, useRef, useState } from 'react'
import clsx from 'clsx'
import { MarkdownBubble } from '@/components/talk/MarkdownBubble'
import { MessageActions } from '@/components/talk/MessageActions'
import type { Message } from './types'

type Props = {
  messages: Message[]                // oldest -> newest
  interimThought: string | null
  loading: boolean
  error?: string
  clearError?: () => void
  feedbackSent: Record<string, boolean>
  onFeedback: (episode_id: string, arm_id: string, utility: number) => void
  onSpeak: (text: string) => void
  hasMore?: boolean
  loadingOlder?: boolean
  onTopThreshold?: () => void
}

const TOP_THRESHOLD_PX = 120
const NEAR_BOTTOM_PX = 80 // how close counts as “at bottom”

function Bubble({
  msg,
  onSpeak,
  parentScrollRef,
}: {
  msg: Message
  onSpeak?: (t: string) => void | Promise<void>
  parentScrollRef?: React.RefObject<HTMLDivElement>
}) {
  const isUser = msg.role === 'user'
  const isAssistant = msg.role === 'ecodia'

  const base = 'rounded-2xl px-4 py-2 shadow-sm leading-6 max-w-full'
  const bubbleCls = [
    base,
    isAssistant && 'bg-white text-neutral-900 border border-neutral-200',
    isUser && 'bg-neutral-800 text-white',
  ].filter(Boolean).join(' ')

  // Forward vertical wheel deltas to parent scroll container so vertical scroll never “sticks”
  const onWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (!parentScrollRef?.current) return
    if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) {
      parentScrollRef.current.scrollTop += e.deltaY
      e.preventDefault()
    }
  }

  return (
    <div
      className={clsx(
        'inline-block align-top max-w-[min(85%,900px)] min-w-0',
        isUser && 'min-w-[12ch]'
      )}
    >
      {/* Horizontal scroller for mega tokens; vertical gestures pass to parent */}
      <div
        className="overflow-x-auto overflow-y-visible hide-scrollbar max-w-full touch-pan-y"
        style={{ overscrollBehaviorX: 'contain' }}
        onWheel={onWheel}
      >
        <div className={clsx(bubbleCls, 'whitespace-pre-wrap break-words')}>
          <MarkdownBubble text={msg.content} />
        </div>
      </div>

      {msg.emotionClass && (
        <div className="mt-1 text-[11px] text-neutral-400">{msg.emotionClass}</div>
      )}

      {/* Assistant-only actions */}
      {isAssistant && onSpeak && (
        <div className="mt-1.5">
          <MessageActions text={msg.content} onSpeak={onSpeak} />
        </div>
      )}
    </div>
  )
}

function RowShell({
  msg,
  children,
  onSpeakRow,
  onFeedbackRow,
  feedbackSent,
}: {
  msg: Message
  children: React.ReactNode
  onSpeakRow: (t: string) => void
  onFeedbackRow: (episode_id: string, arm_id: string, utility: number) => void
  feedbackSent: Record<string, boolean>
}) {
  const isUser = msg.role === 'user'
  const isAssistant = msg.role === 'ecodia'

  return (
    <div className={clsx('w-full flex min-w-0', isUser ? 'justify-end' : 'justify-start')}>
      <div className="flex flex-col items-start min-w-0">
        <div
          onClickCapture={(e) => {
            const target = e.target as HTMLElement
            if (target?.closest('button[aria-label="Say this"]')) {
              onSpeakRow(msg.content || '')
            }
          }}
        >
          {children}
        </div>

        {isAssistant && (msg.episode_id && msg.arm_id) && (
          <div className="mt-1 flex items-center gap-2 text-[11px]">
            <button
              type="button"
              onClick={() => onFeedbackRow(msg.episode_id!, msg.arm_id!, 1)}
              disabled={!!feedbackSent[msg.episode_id!]}
              className="px-2 py-0.5 rounded bg-white/80 text-neutral-900 hover:bg-white disabled:opacity-50"
              title="This was helpful" aria-label="Thumbs up"
            >
              👍
            </button>
            <button
              type="button"
              onClick={() => onFeedbackRow(msg.episode_id!, msg.arm_id!, 0)}
              disabled={!!feedbackSent[msg.episode_id!]}
              className="px-2 py-0.5 rounded bg-white/80 text-neutral-900 hover:bg-white disabled:opacity-50"
              title="This wasn't helpful" aria-label="Thumbs down"
            >
              👎
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

export function ChatList({
  messages,
  interimThought,
  loading,
  error,
  clearError,
  feedbackSent,
  onFeedback,
  onSpeak,
  hasMore,
  loadingOlder,
  onTopThreshold,
}: Props) {
  const items = useMemo(() => {
    if (interimThought) return [...messages, { role: 'ecodia', content: interimThought } as Message]
    return messages
  }, [messages, interimThought])

  const scrollRef = useRef<HTMLDivElement>(null)
  const userNearBottomRef = useRef(true)
  const [showJump, setShowJump] = useState(false)

  const scrollToBottom = () => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }
  const updateNearBottom = () => {
    const el = scrollRef.current
    if (!el) return
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX
    userNearBottomRef.current = near
    setShowJump(!near)
  }

  // On new items, stick to bottom if we're already near bottom
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    if (userNearBottomRef.current) {
      el.scrollTop = el.scrollHeight
      setShowJump(false)
    }
  }, [items.length])

  // Track scroll position to toggle jump button and trigger loading older
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => {
      updateNearBottom()
      if (el.scrollTop <= TOP_THRESHOLD_PX) onTopThreshold?.()
    }
    updateNearBottom()
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [onTopThreshold])

  return (
    <div className="relative w-full h-full flex flex-col min-h-0">
      {/* Scroller */}
      <div
        ref={scrollRef}
        className="flex-1 min-h-0 chat-scroll hide-scrollbar chat-mask-bottom-fade px-4 pt-0 pb-0"
        style={{ ['--chat-fade-bottom' as any]: '8px' }}
      >
        <div className="mx-auto max-w-3xl space-y-2 pb-3">
          {items.map((msg, i) => (
            <RowShell
              key={i}
              msg={msg}
              onSpeakRow={onSpeak}
              onFeedbackRow={onFeedback}
              feedbackSent={feedbackSent}
            >
              <Bubble msg={msg} onSpeak={onSpeak} parentScrollRef={scrollRef} />
            </RowShell>
          ))}
        </div>
      </div>

      {/* Floating "Jump to latest" button */}
      {showJump && (
        <button
          onClick={() => {
            scrollToBottom()
            setShowJump(false)
            userNearBottomRef.current = true
          }}
          className="absolute right-6 bottom-16 z-50 rounded-full px-3 py-2 text-xs
                     bg-white/90 text-neutral-900 shadow hover:bg-white transition"
          aria-label="Jump to latest"
          title="Jump to latest"
        >
          ↓ New messages
        </button>
      )}

      {loadingOlder && (
        <div className="absolute top-1 left-0 right-0 z-10 flex justify-center">
          <div className="rounded bg-black/60 px-2 py-1 text-[11px] text-white">Loading earlier messages…</div>
        </div>
      )}
      {!loadingOlder && hasMore === false && (
        <div className="absolute top-1 left-0 right-0 z-10 flex justify-center">
          <div className="rounded bg-neutral-200 px-2 py-1 text-[11px] text-neutral-700">No more history</div>
        </div>
      )}

      {loading && !interimThought && (
        <div className="absolute bottom-1 left-0 right-0 z-10 flex justify-center">
          <div className="rounded bg-neutral-200 px-2 py-1 text-[11px] text-neutral-700">Thinking…</div>
        </div>
      )}
      {!!error && (
        <div className="absolute bottom-1 left-0 right-0 z-10 flex justify-center">
          <button
            onClick={clearError}
            className="rounded bg-rose-500 px-3 py-1 text-[12px] text-white shadow"
          >
            {error} - dismiss
          </button>
        </div>
      )}
    </div>
  )
}
