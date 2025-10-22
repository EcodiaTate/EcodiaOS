export type TypingInstruction = string // "type:slow" | "pause:400ms" | "glitch" | "backspace:hello,world"

export interface TypingRenderOptions {
  text: string
  meta: TypingInstruction[]
  onCharRender?: (char: string, index: number) => void
  onEmotionClassUpdate?: (emotionClass: string) => void
  onComplete?: () => void
}

export async function simulateTyping({
  text,
  meta,
  onCharRender,
  onEmotionClassUpdate,
  onComplete,
}: TypingRenderOptions) {
  let speed = 30
  const pauseMap = new Map<number, number>()
  const backspaceMap = new Map<number, { from: string; to: string }>()
  const glitchIndices = new Set<number>()
  let emotionClass = ''

  // Parse meta
  meta.forEach((m) => {
    if (m.startsWith('type:')) {
      const t = m.split(':')[1]
      if (t === 'slow') speed = 75
      if (t === 'medium') speed = 40
      if (t === 'fast') speed = 15
    }

    if (m.startsWith('pause:')) {
      const ms = parseInt(m.split(':')[1])
      const idx = text.length - 1
      pauseMap.set(idx, ms)
    }

    if (m.startsWith('backspace:')) {
      const content = m.split(':')[1]
      const [from, to] = content.split(',').map(s => s.trim())
      const idx = text.length - 1
      backspaceMap.set(idx, { from, to })
    }

    if (m === 'glitch') {
      for (let i = 0; i < Math.min(text.length, 5); i++) {
        glitchIndices.add(i)
      }
    }

    if (m.startsWith('emotion:')) {
      const emotion = m.split(':')[1]
      switch (emotion) {
        case 'joy': emotionClass = 'emotion-glow'; break
        case 'sadness': emotionClass = 'emotion-fade'; break
        case 'anger': emotionClass = 'emotion-shake'; break
        case 'fear': emotionClass = 'emotion-blur'; break
        case 'calm': emotionClass = 'emotion-soft'; break
        default: emotionClass = ''
      }
    }
  })

  if (onEmotionClassUpdate) {
    onEmotionClassUpdate(emotionClass)
  }

  // Typing loop
  let display = ''
  for (let i = 0; i < text.length; i++) {
    const char = text[i]

    if (glitchIndices.has(i)) {
      const glitchChar = ['@', '#', '*', '∆', '%'][Math.floor(Math.random() * 5)]
      onCharRender?.(glitchChar, i)
      await wait(speed / 2)
    }

    display += char
    onCharRender?.(char, i)

    if (pauseMap.has(i)) {
      await wait(pauseMap.get(i)!)
    } else {
      await wait(speed)
    }
  }

  // Handle expressive backspace after typing
  for (const [_, { from, to }] of backspaceMap.entries()) {
    await wait(500)

    for (let i = 0; i < from.length; i++) {
      display = display.slice(0, -1)
      onCharRender?.('', display.length)
      await wait(40)
    }

    await wait(150)

    for (let i = 0; i < to.length; i++) {
      const char = to[i]
      display += char
      onCharRender?.(char, display.length - 1)
      await wait(30)
    }
  }

  onComplete?.()
}

function wait(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms))
}
