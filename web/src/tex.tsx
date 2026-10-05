import { useSyncExternalStore, type ReactNode } from 'react'
import { getEpoch, loadKatex, loadedKatex, subscribe, texEnabled, type Katex } from './texStore'

// Same delimiters as linXiv desktop (src/lib/tex.tsx): $$…$$ (display) or
// $…$ (inline, one line, no space just inside either $). An unpaired opener
// such as the first $ in "$5 and $6" matches nothing.
const MATH_RE = /\$\$([\s\S]+?)\$\$|\$(?!\s)([^$\n]*?[^$\s])\$/g

function mathHtml(k: Katex, tex: string, display: boolean): string | null {
  if (!tex.trim()) return null
  try {
    // trust: false (default) blocks \href, \url, \includegraphics and friends.
    return k.renderToString(tex, { displayMode: display, throwOnError: true, strict: 'ignore' })
  } catch {
    return null
  }
}

function toNodes(k: Katex, text: string, forceInline: boolean): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  let key = 0
  for (const m of text.matchAll(MATH_RE)) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const isDisplay = m[1] !== undefined
    const html = mathHtml(k, (isDisplay ? m[1] : m[2]) as string, isDisplay && !forceInline)
    // Unrenderable TeX keeps its raw, delimited source.
    nodes.push(html === null ? m[0] : <span key={key++} dangerouslySetInnerHTML={{ __html: html }} />)
    last = m.index + m[0].length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

/** Text with $…$ / $$…$$ rendered by KaTeX when TeX rendering is enabled.
 * `forceInline` keeps $$…$$ inline, for titles and other one-line spots. */
export function MathText({ children, forceInline = false }: { children?: string | null; forceInline?: boolean }) {
  useSyncExternalStore(subscribe, getEpoch)
  const text = children ?? ''
  if (!texEnabled() || !text.includes('$')) return <>{text}</>
  const katex = loadedKatex()
  if (!katex) {
    loadKatex()
    return <>{text}</>
  }
  return <>{toNodes(katex, text, forceInline)}</>
}
