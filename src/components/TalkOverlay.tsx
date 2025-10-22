'use client'

import React, { useEffect, useRef, useState, useCallback } from 'react'
import SpeechRecognition, { useSpeechRecognition } from 'react-speech-recognition'
import { BackToHubButton } from '@/components/ui'
import { useSoulStore } from '@/stores/useSoulStore'
import { useRenderStore } from '@/stores/useRenderStore'
import { useVoiceStore } from '@/stores/useVoiceStore'
import { ConsentToast, type ProfileUpsert } from '@/components/ConsentToast'
import { ChatList } from '@/components/talk/ChatList'
import { InputBar } from '@/components/talk/InputBar'
import { simulateTyping } from '@/lib/expressive/typingRenderer'
import { formatExpressiveResponse } from '@/lib/expressive/formatter'

import type { Message } from '@/components/talk/types'
import { stripTags, ECODIA_FAILURE_LINES, pick } from '@/components/talk/utils'

// ----------- paging / window config -----------
const HISTORY_PAGE_SIZE = 30
const WINDOW_MAX_MESSAGES = 300
const TOP_SCROLL_THRESHOLD = 80

// Throttling/timeout knobs
const HISTORY_FETCH_TIMEOUT_MS = 12000
const HISTORY_MIN_INTERVAL_MS = 500 // cooldown between loads

export default function TalkOverlay() {
  const soulId = useSoulStore((s) => s.soulId)
  const userUuid = useSoulStore((s) => s.userUuid)
  const { outputMode, setOutputMode } = useRenderStore()
  const setIsPlaying = useVoiceStore((s) => s.setIsPlaying)

  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [feedbackSent, setFeedbackSent] = useState<Record<string, boolean>>({})
  const [interimThought, setInterimThought] = useState<string | null>(null)

  // history state
  const [hasMore, setHasMore] = useState(true)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [initialHistoryLoaded, setInitialHistoryLoaded] = useState(false)
  const [beforeCursor, setBeforeCursor] = useState<string | null>(null)

  // jump-to-bottom
  const [showJumpToBottom, setShowJumpToBottom] = useState(false)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)
  const talkAbortRef = useRef<AbortController | null>(null)
  const ttsAbortRef = useRef<AbortController | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const chatScrollRef = useRef<HTMLDivElement | null>(null)

  const MAX_TEXTAREA_PX = 5 * 20 + 12

  const resolvedUserId =
    userUuid || (typeof window !== 'undefined' ? localStorage.getItem('user_uuid') : null) || 'user_anon'

  const {
    transcript,
    listening,
    resetTranscript,
    browserSupportsSpeechRecognition,
  } = useSpeechRecognition()

  // cleanup with aborts swallowed
  useEffect(() => {
    return () => {
      try { cleanupAudio() } catch {}
      try { talkAbortRef.current?.abort() } catch {}
      try { ttsAbortRef.current?.abort() } catch {}
      try {
        if (historyAbortRef.current) {
          // @ts-ignore give a reason if supported
          historyAbortRef.current.abort?.('cleanup')
        }
      } catch {}
      historyAbortRef.current = null
    }
  }, [])

  const cleanupAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ''
      audioRef.current = null
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current)
      audioUrlRef.current = null
    }
    setIsPlaying(false)
  }

  const stopPlaybackAndListening = () => {
    cleanupAudio()
    if (listening) SpeechRecognition.stopListening()
    talkAbortRef.current?.abort()
    ttsAbortRef.current?.abort()
  }

  const addPlaceholder = (msg: Message): number => {
    let index = -1
    setMessages((prev) => {
      const next = [...prev, msg]
      // rolling window on append
      const overflow = Math.max(0, next.length - WINDOW_MAX_MESSAGES)
      if (overflow > 0) next.splice(0, overflow)
      index = next.length - 1
      return next
    })
    return index
  }

  const prependMessages = (older: Message[]) => {
    setMessages((prev) => {
      const next = [...older, ...prev]
      const overflow = Math.max(0, next.length - WINDOW_MAX_MESSAGES)
      if (overflow > 0) next.splice(0, overflow) // drop oldest overall
      return next
    })
  }

  const replaceMessageAt = (index: number, updater: (m: Message) => Message) => {
    setMessages((prev) => {
      if (!prev[index]) return prev
      const next = [...prev]
      next[index] = updater(next[index])
      return next
    })
  }

  // ----- sticky-to-bottom behavior -----
  const stickToBottomRef = useRef(true)
  const isNearBottom = (el: HTMLDivElement, threshold = 80) =>
    el.scrollHeight - el.scrollTop - el.clientHeight < threshold

  const scrollToBottom = () => {
    const el = chatScrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }

  const autoSizeTextarea = () => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    const newHeight = Math.min(ta.scrollHeight, MAX_TEXTAREA_PX)
    ta.style.height = `${newHeight}px`
    ta.style.overflowY = ta.scrollHeight > newHeight ? 'auto' : 'hidden'
  }

  useEffect(() => { autoSizeTextarea() }, [input, transcript, listening])

  // ----------------- History fetch helpers -----------------
  const historyAbortRef = useRef<AbortController | null>(null)
  const historyInFlightRef = useRef(false)
  const lastHistoryLoadAtRef = useRef<number>(0)
  const topLatchRef = useRef(false) // prevents repeat triggers while parked at top

  const fetchHistory = useCallback(
    async (opts: { before?: string | null; limit?: number } = {}) => {
      if (!soulId) return [] as Message[]

      const params = new URLSearchParams({
        session_id: soulId,
        limit: String(opts.limit ?? HISTORY_PAGE_SIZE),
      })
      if (opts.before) params.set('before', opts.before)

      // cancel any previous in-flight history request
      try { historyAbortRef.current?.abort() } catch {}
      historyAbortRef.current = new AbortController()

      try {
        const res = await fetch(`/api/voxis/history?${params.toString()}`, {
          cache: 'no-store',
          signal: historyAbortRef.current.signal,
        })
        if (!res.ok) throw new Error(await res.text())

        // backend returns NEWEST → OLDEST; flip to chronological for rendering
        const page = await res.json() as {
          id: string; role: 'user' | 'assistant'; content: string; created_at: string
        }[]

        return page.reverse().map((r) => ({
          id: r.id,
          role: r.role === 'assistant' ? 'ecodia' : 'user',
          content: r.content || '',
          created_at: r.created_at,
        }) as Message)
      } catch (e: any) {
        // swallow user-initiated aborts
        if (e?.name === 'AbortError') return []
        throw e
      } finally {
        historyAbortRef.current = null
      }
    },
    [soulId]
  )

  const loadInitialHistory = useCallback(async () => {
    if (!soulId) return
    try {
      historyInFlightRef.current = true
      lastHistoryLoadAtRef.current = Date.now()
      const page = await fetchHistory()
      setMessages(page)
      setHasMore(page.length === HISTORY_PAGE_SIZE)
      setInitialHistoryLoaded(true)
      setBeforeCursor(page.length ? page[0].created_at! : null)
      topLatchRef.current = false

      // force start at latest (double-rAF ensures layout complete)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          scrollToBottom()
          stickToBottomRef.current = true
          setShowJumpToBottom(false)
        })
      })
    } catch (e) {
      console.error('[TalkOverlay] loadInitialHistory failed:', e)
      setInitialHistoryLoaded(true)
    } finally {
      historyInFlightRef.current = false
    }
  }, [fetchHistory, soulId])

  const loadOlderHistory = useCallback(async () => {
    if (!soulId || !hasMore || loadingOlder || !beforeCursor) return
    const now = Date.now()
    if (now - lastHistoryLoadAtRef.current < HISTORY_MIN_INTERVAL_MS) return
    if (historyInFlightRef.current) return

    historyInFlightRef.current = true
    lastHistoryLoadAtRef.current = now
    setLoadingOlder(true)

    const container = chatScrollRef.current
    const prevScrollHeight = container?.scrollHeight ?? 0
    const prevScrollTop = container?.scrollTop ?? 0

    try {
      const older = await fetchHistory({ before: beforeCursor })
      if (!older.length) {
        setHasMore(false)
        return
      }
      setBeforeCursor(older[0].created_at || beforeCursor)
      prependMessages(older)

      requestAnimationFrame(() => {
        if (!container) return
        const newScrollHeight = container.scrollHeight
        const delta = newScrollHeight - prevScrollHeight
        container.scrollTop = prevScrollTop + delta
      })

      if (older.length < HISTORY_PAGE_SIZE) setHasMore(false)
    } catch (e) {
      console.error('[TalkOverlay] loadOlderHistory failed:', e)
    } finally {
      setLoadingOlder(false)
      historyInFlightRef.current = false
    }
  }, [soulId, hasMore, loadingOlder, beforeCursor, fetchHistory])

  useEffect(() => {
    setMessages([])
    setHasMore(true)
    setInitialHistoryLoaded(false)
    setBeforeCursor(null)
    topLatchRef.current = false
    try { historyAbortRef.current?.abort() } catch {}
    if (soulId) {
      loadInitialHistory()
    }
  }, [soulId, loadInitialHistory])

  // rAF-throttled scroll listener + top latch + sticky-bottom tracking + jump button
  const scrollRafRef = useRef<number | null>(null)
  const onScroll = useCallback(() => {
    const el = chatScrollRef.current
    if (!el) return
    if (scrollRafRef.current != null) return
    scrollRafRef.current = requestAnimationFrame(() => {
      scrollRafRef.current = null

      // update sticky-bottom + button visibility
      const near = isNearBottom(el)
      stickToBottomRef.current = near
      setShowJumpToBottom(!near)

      if (loadingOlder || !hasMore) return

      const st = el.scrollTop
      // release the latch once user leaves the top zone
      if (st > TOP_SCROLL_THRESHOLD + 40) {
        topLatchRef.current = false
      }
      if (st <= TOP_SCROLL_THRESHOLD && !topLatchRef.current) {
        topLatchRef.current = true // latch so we don't spam while parked
        loadOlderHistory()
      }
    })
  }, [hasMore, loadingOlder, loadOlderHistory])

  useEffect(() => {
    const el = chatScrollRef.current
    if (!el) return
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      el.removeEventListener('scroll', onScroll)
      if (scrollRafRef.current != null) cancelAnimationFrame(scrollRafRef.current)
    }
  }, [onScroll])

  // If new messages arrive and the user is near bottom, snap to bottom
  useEffect(() => {
    const el = chatScrollRef.current
    if (!el) return
    if (stickToBottomRef.current) {
      requestAnimationFrame(() => requestAnimationFrame(scrollToBottom))
    }
  }, [messages.length])

  // --- networking & flows ----------------------------------------------------

  const sendMessage = async (textToSend: string) => {
    const content = textToSend.trim()
    if (!content || loading) return
    if (!soulId) { setError(pick(ECODIA_FAILURE_LINES)); return }

    stopPlaybackAndListening()
    addPlaceholder({ role: 'user', content })
    setInput('')
    resetTranscript()
    setLoading(true)
    setInterimThought(null)
    setError('')
    autoSizeTextarea()

    try {
      const ctrl = new AbortController()
      talkAbortRef.current = ctrl

      const initialRes = await fetch('/api/voxis/talk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_input: content,
          user_id: resolvedUserId,
          soul_event_id: soulId,
          output_mode: outputMode
        }),
        signal: ctrl.signal,
      })
      if (!initialRes.ok) {
        const errData = await initialRes.json().catch(() => ({ error: 'Request failed' }))
        throw new Error(errData.error || 'Initial API request failed')
      }

      let finalData: any
      if (initialRes.status === 202) {
        const { decision_id } = await initialRes.json()
        if (!decision_id) throw new Error('Decision ID not provided by the server for polling.')

        const POLL_TIMEOUT_MS = 3 * 60 * 1000
        const POLL_BASE_DELAY = 1000
        const POLL_MAX_DELAY = 5000
        const BACKOFF_FACTOR = 1.2

        const pollUntilComplete = async (): Promise<any> => {
          const deadline = Date.now() + POLL_TIMEOUT_MS
          let attempt = 0
          while (Date.now() < deadline) {
            if (ctrl.signal.aborted) throw new Error('Request aborted')
            const pollRes = await fetch(`/api/voxis/talk?result_id=${decision_id}`, { cache: 'no-store', signal: ctrl.signal })
            if (pollRes.status === 200) return pollRes.json()
            if (pollRes.status === 202) {
              try {
                const pollData = await pollRes.json()
                if (pollData?.interim_thought && !interimThought) {
                  setInterimThought(pollData.interim_thought)
                }
              } catch {}
              const retryAfter = pollRes.headers.get('Retry-After')
              const delay = retryAfter && !Number.isNaN(Number(retryAfter))
                ? Number(retryAfter) * 1000
                : Math.min(POLL_BASE_DELAY * Math.pow(BACKOFF_FACTOR, attempt), POLL_MAX_DELAY)
              attempt++
              await new Promise((r) => setTimeout(r, delay))
              continue
            }
            const errData = await pollRes.json().catch(() => ({ error: 'Polling failed' }))
            throw new Error(errData.error || `Polling returned status ${pollRes.status}`)
          }
          throw new Error('Response timed out.')
        }

        finalData = await pollUntilComplete()
      } else {
        finalData = await initialRes.json()
      }
      setInterimThought(null)

      const profileUpsert = finalData.profile_upserts?.[0]
      if (profileUpsert?.updates) {
        const property = Object.keys(profileUpsert.updates)[0]
        const value = profileUpsert.updates[property]
        if (property && value) setConsentRequest({ property, value, raw_data: profileUpsert })
      }

      const raw = String(finalData.expressive_text ?? '').trim()
      const ecodiaMsg: Message = {
        role: 'ecodia',
        content: raw || '(No response text)',
        episode_id: finalData.episode_id,
        arm_id: finalData.arm_id,
      }

      setLoading(false)

      if (finalData.mode === 'voice' || outputMode === 'voice') {
        await renderVoiceResponse(ecodiaMsg)
      } else {
        await renderTypingResponse(ecodiaMsg)
      }

      requestAnimationFrame(() => requestAnimationFrame(scrollToBottom))
    } catch (err: any) {
      if (err.name === 'AbortError') return
      console.error('[TalkOverlay] Error:', err)
      setError(pick(ECODIA_FAILURE_LINES))
      addPlaceholder({ role: 'ecodia', content: '- That path fizzled. One more try?' })
    } finally {
      setLoading(false)
      talkAbortRef.current = null
    }
  }

  const [consentRequest, setConsentRequest] = useState<ProfileUpsert | null>(null)

  const renderVoiceResponse = async (msg: Message) => {
    const cleanText = stripTags(msg.content)
    const placeholderIndex = addPlaceholder({ ...msg, content: '', ttsPending: true })

    try {
      const ctrl = new AbortController()
      ttsAbortRef.current = ctrl

      const ttsResponse = await fetch('/api/tts/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: msg.content }), signal: ctrl.signal,
      })
      if (!ttsResponse.ok) throw new Error('TTS generation failed')

      const audioBlob = await ttsResponse.blob()
      const audioUrl = URL.createObjectURL(audioBlob)
      audioUrlRef.current = audioUrl

      replaceMessageAt(placeholderIndex, () => ({ ...msg, content: cleanText || '(No response text)', ttsPending: false }))

      const audio = new Audio(audioUrl)
      audioRef.current = audio
      audio.onplay = () => setIsPlaying(true)
      audio.onended = () => cleanupAudio()
      audio.onerror = () => cleanupAudio()

      await audio.play()
    } catch (err: any) {
      if (err.name === 'AbortError') { cleanupAudio(); return }
      console.error('[TalkOverlay] Voice playback error:', err)
      cleanupAudio()
      replaceMessageAt(placeholderIndex, () => ({ ...msg, content: `(Voice error) ${cleanText || ''}`.trim() }))
    } finally {
      ttsAbortRef.current = null
    }
  }

  const renderTypingResponse = async (msg: Message) => {
    let { cleanText } = formatExpressiveResponse(msg.content || '', 'typing')
    if (!cleanText) cleanText = (msg.content || '').replace(/\[[^\]]*?\]/g, '').replace(/\s{2,}/g, ' ').trim()
    if (!cleanText) { addPlaceholder({ ...msg, content: '(No response text)', emotionClass: '' }); return }

    const targetIndex = addPlaceholder({ ...msg, content: cleanText, emotionClass: '' })
    try {
      let typed = ''
      await simulateTyping({
        text: cleanText, meta: [],
        onCharRender: (char) => {
          if (char === '') typed = typed.slice(0, -1); else typed += char
          if (typed.length && typed.length <= cleanText.length) {
            replaceMessageAt(targetIndex, (m) => ({ ...m, content: typed }))
          }
        },
        onEmotionClassUpdate: (emotionClass) => {
          replaceMessageAt(targetIndex, (m) => ({ ...m, emotionClass }))
        },
      })
      replaceMessageAt(targetIndex, (m) => ({ ...m, content: cleanText }))
    } catch { /* keep full text on animation error */ }
  }

  const handleFeedback = async (episode_id: string, arm_id: string, utility: number) => {
    if (!episode_id || !arm_id) return
    if (feedbackSent[episode_id]) return
    setFeedbackSent((prev) => ({ ...prev, [episode_id]: true }))

    const idempotencyKey = `${episode_id}::${utility}`
    try {
      const res = await fetch('/api/voxis/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey },
        body: JSON.stringify({ episode_id, arm_id, chosen_arm_id: arm_id, utility, meta: { source: 'overlay_button' } }),
      })
      if (!res.ok) console.warn('[TalkOverlay] Feedback not routed cleanly:', res.status, await res.text())
    } catch (e) {
      console.warn('[TalkOverlay] Feedback failed:', e)
    }
  }

  const onSpeak = async (text: string) => { await renderVoiceResponse({ role: 'ecodia', content: text }) }

  // --- render ---------------------------------------------------------------

  return (
    <div className="absolute inset-0 z-40 flex flex-col bg-transparent isolate font-[var(--font-primary)]" aria-live="polite">
      <ConsentToast
        isVisible={!!consentRequest}
        upsert={consentRequest}
        onAccept={(up) => handleConsentAccept(up)}
        onDecline={() => setConsentRequest(null)}
      />

      {/* CHAT AREA */}
      <div
        ref={chatScrollRef}
        className="flex-1 min-h-0 chat-scroll hide-scrollbar chat-mask-bottom-fade px-4 pt-0 pb-0"
        style={{ ['--chat-fade-bottom' as any]: '8px' }}  // shorter fade so latest isn’t covered
      >
        <ChatList
          interimThought={interimThought}
          messages={messages}
          loading={loading || !initialHistoryLoaded}
          feedbackSent={feedbackSent}
          onFeedback={handleFeedback}
          onSpeak={onSpeak}
          error={error}
          clearError={() => { setError(''); textareaRef.current?.focus() }}
          hasMore={hasMore}
          loadingOlder={loadingOlder}
          onTopThreshold={loadOlderHistory}
        />
      </div>

      {/* Jump-to-bottom button */}
      {showJumpToBottom && (
        <button
          onClick={() => { scrollToBottom(); stickToBottomRef.current = true; setShowJumpToBottom(false) }}
          className="absolute right-6 bottom-[88px] z-50 rounded-full px-3 py-2 text-xs bg-white/90 text-neutral-900 shadow hover:bg-white"
          aria-label="Jump to latest"
          title="Jump to latest"
        >
          ↓ New messages
        </button>
      )}

      {/* INPUT BAR */}
      <div className="w-full px-4 pt-0 pb-3 pointer-events-auto">
        <div className="input-bar-wrap">
          <InputBar
            outputMode={outputMode}
            setOutputMode={setOutputMode}
            listening={listening}
            browserSupportsSpeechRecognition={browserSupportsSpeechRecognition}
            loading={loading}
            textareaRef={textareaRef}
            inputValue={input}
            transcriptValue={transcript}
            onChangeInput={(v) => {
              setInput(v)
              const ta = textareaRef.current
              if (ta) {
                ta.style.height = 'auto'
                const newH = Math.min(ta.scrollHeight, MAX_TEXTAREA_PX)
                ta.style.height = `${newH}px`
                ta.style.overflowY = ta.scrollHeight > newH ? 'auto' : 'hidden'
              }
            }}
            onSubmit={(text) => sendMessage(text)}
            onStartListening={() => SpeechRecognition.startListening()}
            onStopListening={() => SpeechRecognition.stopListening()}
            onStopAll={stopPlaybackAndListening}
            audioActive={!!audioRef.current}
          />
        </div>
      </div>

      <div className="pointer-events-auto self-center pb-3">
        <BackToHubButton />
      </div>
    </div>
  )

  async function handleConsentAccept(upsert: ProfileUpsert) {
    setConsentRequest(null)
    try {
      const res = await fetch('/api/voxis/profile/consent', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: resolvedUserId, profile_upserts: [upsert.raw_data] }),
      })
      if (!res.ok) console.warn('Profile update failed:', await res.text())
    } catch (error) { console.error('Error sending profile consent:', error) }
  }
}
