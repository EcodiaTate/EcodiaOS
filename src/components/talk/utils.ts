export const stripTags = (s: string) =>
  (s || '').replace(/\[[^\]]*?\]/g, '').replace(/\s{2,}/g, ' ').trim()

// utils.ts
// utils.ts
export function normalizeMarkdown(text: string): string {
  return text
    .split(/(```[\s\S]*?```)/g)
    .map((seg) => {
      if (seg.startsWith('```')) return seg;

      // 1) 🔓 Unescape common double-escaped sequences (outside code fences)
      seg = seg
        .replace(/\\r\\n/g, '\n')
        .replace(/\\n/g, '\n')
        .replace(/\\t/g, '\t')
        .replace(/<br\s*\/?>/gi, '\n')      // HTML <br> -> newline
        .replace(/&nbsp;/gi, ' ');

      // 2) Normalize odd chars
      return seg
        .replace(/\r\n/g, '\n')
        .replace(/\u00A0/g, ' ')
        .replace(/\u200B|\u200C|\u200D/g, '')
        .replace(/\uFF03/g, '#')

        // Headings: ensure on own line + space after hashes
        .replace(/([^\n])\s(#{1,6}\s)/g, '$1\n$2')
        .replace(/(^|\n)(#{1,6})([^\s#])/g, '$1$2 $3')
        .replace(/([^\n])\n(#{1,6}\s)/g, '$1\n\n$2')

        // Horizontal rules isolated
        .replace(/(^|\n)[ \t]*(-{3,}|_{3,}|\*{3,})[ \t]*(?=\n|$)/g, '\n\n---\n\n')

        // Ensure a blank line BEFORE any list block
        .replace(/([^\n])\n(\s*(?:\d+[.)]|\-|\+|\*)\s+)/g, '$1\n\n$2')

        // Ensure list markers have a space
        .replace(/(^|\n)(\s*\d+[.)])([^\s.])/g, '$1$2 $3')
        .replace(/(^|\n)(\s*[\-\+\*])([^\s])/g, '$1$2 $3')

        // Make list items "loose": add a blank line BETWEEN consecutive items
        .replace(/(^|\n)(\s*(?:\d+[.)]))\s+([^\n]+)\n(?!\n)(?=\s*\d+[.)]\s)/g, '$1$2 $3\n\n')
        .replace(/(^|\n)(\s*[\-\+\*])\s+([^\n]+)\n(?!\n)(?=\s*[\-\+\*]\s)/g, '$1$2 $3\n\n')

        .trim();
    })
    .join('');
}



export const ECODIA_FAILURE_LINES = [
  "That didn't land. Want me to take another run at it?",
  'Hmm—no joy on that one. Nudge me with a hint, or tap retry.',
  'I lost the thread there. Give me another cue or hit retry.',
  'That path fizzled. One more try? I’ll tighten it up.',
]

export const pick = <T,>(arr: T[]) => arr[Math.floor(Math.random() * arr.length)]
