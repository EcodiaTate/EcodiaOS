interface VoiceMeta {
  speech?: string
  emotion?: string
}

export async function speakWithVoice(text: string, meta: VoiceMeta) {
  const payload: {
    text: string
    voice_settings: {
      stability: number
      similarity_boost: number
    }
    style: string
    emotion: string
  } = {
    text,
    voice_settings: {
      stability: 0.5,
      similarity_boost: 0.75,
    },
    style: meta.speech ?? 'conversational',
    emotion: meta.emotion ?? 'neutral',
  }

  const response = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    throw new Error(`Voice rendering failed: ${response.statusText}`)
  }

  const blob = await response.blob()
  const url = URL.createObjectURL(blob)

  const audio = new Audio(url)
  await audio.play()
}
