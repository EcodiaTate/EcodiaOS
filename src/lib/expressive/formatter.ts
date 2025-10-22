export type OutputMode = 'typing' | 'voice'

export interface ExpressiveOutput {
  cleanText: string
  typingMeta: string[]               // e.g., ['pause:600','type:fast','glitch','backspace:12,5']
  voiceMeta: Record<string, string>  // e.g., { emotion:'warm', speech:'whisper' }
}

const TAG_PATTERN = /\[([^\]]+)\]/g

export function formatExpressiveResponse(text: string, outputMode: OutputMode): ExpressiveOutput {
  const typingMeta: string[] = []
  const voiceMeta: Record<string, string> = {}

  const tags: string[] = []
  let m: RegExpExecArray | null
  while ((m = TAG_PATTERN.exec(text)) !== null) tags.push(m[1])

  // Normalize/map each tag to something your system understands
  for (const raw of tags) {
    const n = normalizeTag(raw) // returns something like 'pause:600', 'type:fast', 'emotion:warm', 'glitch', etc.
    if (!n) continue

    const [key, ...rest] = n.split(':')
    const value = rest.join(':') // keep any extra colons

    switch (key) {
      case 'glitch':
      case 'pause':
      case 'type':
        if (outputMode === 'typing') typingMeta.push(value ? `${key}:${value}` : key)
        break

      case 'backspace':
        if (outputMode === 'typing') typingMeta.push(`backspace:${value}`)
        break

      case 'emotion':
      case 'speech':
        if (outputMode === 'voice') voiceMeta[key] = value || ''
        break

      default:
        // Unknown (after normalization) — silently ignore
        break
    }
  }

  const cleanText = text.replace(TAG_PATTERN, '').replace(/\s{2,}/g, ' ').trim()
  return { cleanText, typingMeta, voiceMeta }
}

/* ---------------- helpers ---------------- */

function normalizeTag(s: string): string | null {
  // lower, trim, collapse spaces; drop leading/trailing punctuation
  let t = s.toLowerCase().trim().replace(/^[\s,:;.-]+|[\s,:;.-]+$/g, '')
  // remove common filler words that LLMs add to style notes
  t = t
    .replace(/\b(with|a|an|the|tone|brief|little|slight|soft|gentle)\b/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim()

  // Explicit DSL passthroughs are already supported by your system:
  // [pause:800], [type:slow], [backspace:from,to], [glitch], [speech:whisper], [emotion:warm]
  if (/^(pause|type|backspace|glitch|speech|emotion):/i.test(t) || t === 'glitch') return t

  // Heuristics & synonyms → map free-text to supported keys
  // Pauses
  if (t === 'pause' || t === 'thoughtful pause') return 'pause:600'
  if (t === 'short pause') return 'pause:350'
  if (t === 'long pause') return 'pause:1200'

  // Pacing
  if (t === 'slowly' || t === 'speak slowly') return 'type:slow'
  if (t === 'quickly' || t === 'faster' || t === 'fast') return 'type:fast'
  if (t === 'leaning in' || t === 'lean in' || t === 'leans in') return 'type:fast'

  // Emotions (voice-only; harmless to include—typing ignores)
  if (t === 'warm' || t === 'warm tone' || t === 'smiling') return 'emotion:warm'
  if (t === 'curiously' || t === 'curious' || t === 'inquisitive') return 'emotion:curious'
  if (t === 'thoughtful') return 'emotion:thoughtful'
  if (t === 'confident') return 'emotion:confident'
  if (t === 'encouraging') return 'emotion:encouraging'
  if (t === 'serious') return 'emotion:serious'
  if (t === 'whisper') return 'speech:whisper'

  // If the tag contains obvious cues, interpret them:
  if (/pause/.test(t)) return 'pause:600'
  if (/warm/.test(t)) return 'emotion:warm'
  if (/curious/.test(t)) return 'emotion:curious'

  // Unknown → ignore quietly
  return null
}
