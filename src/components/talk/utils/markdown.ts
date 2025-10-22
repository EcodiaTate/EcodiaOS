// utils/markdown.ts
import { unified } from 'unified'
import remarkParse from 'remark-parse'
import remarkGfm from 'remark-gfm'
import remarkRehype from 'remark-rehype'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import rehypeStringify from 'rehype-stringify'

// ✅ types + default schema come from hast-util-sanitize
import { defaultSchema } from 'hast-util-sanitize'
import type { Schema } from 'hast-util-sanitize'

// extend the schema just a touch so Tailwind prose + code classes work
const schema: Schema = {
  ...defaultSchema,
  attributes: {
    ...(defaultSchema.attributes ?? {}),
    code: [
      ...(defaultSchema.attributes?.code ?? []),
      ['className', /^language-/], // keep syntax highlight classes
    ],
  },
}

const processor = unified()
  .use(remarkParse)
  .use(remarkGfm)
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeRaw)
  .use(rehypeSanitize, schema) // pass the Schema directly
  .use(rehypeStringify)

export async function renderMarkdown(source: string) {
  const file = await processor.process(source ?? '')
  return String(file)
}
