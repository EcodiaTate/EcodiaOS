'use client'
import React from 'react'
import { renderMarkdown } from '@/components/talk/utils/markdown'

export function MarkdownBubble({ text }: { text: string }) {
  const [html, setHtml] = React.useState('')

  React.useEffect(() => {
    let alive = true
    renderMarkdown(text).then((out) => alive && setHtml(out))
    return () => { alive = false }
  }, [text])

  return (
    <div
      className="prose prose-invert prose-sm max-w-none markdown-chat
                 prose-pre:whitespace-pre-wrap prose-pre:break-words
                 prose-p:leading-relaxed prose-li:my-1
                 prose-code:px-1 prose-code:py-0.5 prose-code:bg-white/5 prose-code:rounded"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}
