'use client'

import React, { MutableRefObject } from 'react'
import { Mic, StopCircle, Send } from 'lucide-react'
import { ModeSwitch } from './ModeSwitch'
import { VoiceHUD } from './VoiceHUD'

type Mode = 'typing' | 'voice'

export function InputBar({
  className = '',                 // <-- NEW: let parent control external spacing
  outputMode,
  setOutputMode,
  listening,
  browserSupportsSpeechRecognition,
  loading,
  textareaRef,
  inputValue,
  transcriptValue,
  onChangeInput,
  onSubmit,
  onStartListening,
  onStopListening,
  onStopAll,
  audioActive,
}: {
  className?: string
  outputMode: Mode
  setOutputMode: (m: Mode) => void
  listening: boolean
  browserSupportsSpeechRecognition: boolean
  loading: boolean
  textareaRef: MutableRefObject<HTMLTextAreaElement | null>
  inputValue: string
  transcriptValue: string
  onChangeInput: (v: string) => void
  onSubmit: (text: string) => void
  onStartListening: () => void
  onStopListening: () => void
  onStopAll: () => void
  audioActive: boolean
}) {
  const value = outputMode === 'voice' ? transcriptValue : inputValue

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(value) }}
      // no external padding; compact internals; no unintended margins
      className={[
        'w-full rounded-2xl border border-white/10',
        'bg-[#0b0b0b]/60 backdrop-blur-md shadow-lg',
        'flex items-center gap-2',
        // keep the height tight without pushing the chat up
        'px-2 py-1',                    // compact container padding
        className,
      ].join(' ')}
    >
      {/* Left controls */}
      <div className="flex items-center gap-1 pr-1">
        <ModeSwitch
          mode={outputMode}
          onChange={(m) => {
            setOutputMode(m)
            if (m === 'typing' && listening) onStopListening()
          }}
          disabled={loading}
        />
        <VoiceHUD active={outputMode === 'voice' && (listening || audioActive)} />
      </div>

      {/* Textarea */}
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChangeInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault(); onSubmit(value)
          }
          if (e.key === 'Escape') onStopAll()
        }}
        placeholder={
          outputMode === 'voice'
            ? 'Listening… (press Stop to finish)'
            : 'Speak or type to Ecodia… (Shift+Enter for newline)'
        }
        rows={1}
        className={[
          'flex-1 bg-transparent text-white placeholder-white/40 focus:outline-none',
          'resize-none text-sm leading-5 min-h-[2.25rem] max-h-36 overflow-y-auto break-words',
          // compact inner padding so the overall bar height stays minimal
          'px-3 py-1.5',
        ].join(' ')}
        disabled={loading}
        aria-label="Message input"
      />

      {/* Right controls */}
      <div className="flex items-center gap-1 w-auto">
        {outputMode === 'voice' && browserSupportsSpeechRecognition ? (
          <>
            {listening ? (
              <button
                type="button"
                onClick={onStopListening}
                className="p-2 rounded-lg text-red-400 bg-white/10 hover:bg-white/15 transition"
                title="Stop listening" aria-label="Stop listening" aria-pressed="true" disabled={loading}
              >
                <StopCircle size={18} />
              </button>
            ) : (
              <button
                type="button"
                onClick={onStartListening}
                className="p-2 rounded-lg text-white/80 hover:text-white bg-white/5 hover:bg-white/10 transition"
                title="Start listening" aria-label="Start listening" aria-pressed="false" disabled={loading}
              >
                <Mic size={18} />
              </button>
            )}
          </>
        ) : null}

        <button
          type="submit"
          className="ml-auto px-3 py-1.5 rounded-xl bg-white/10 text-white/80 hover:bg-white/20 transition disabled:opacity-50 inline-flex items-center gap-1"
          disabled={loading} title="Send" aria-label="Send"
        >
          <Send size={16} /> <span className="hidden sm:inline">Send</span>
        </button>
      </div>
    </form>
  )
}
