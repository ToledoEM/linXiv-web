import { useSyncExternalStore, type ReactNode } from 'react'

type Katex = typeof import('katex').default

// Store for the `tex_rendering_enabled` setting plus the lazily loaded KaTeX
// module; components re-render when either changes.
let enabled = true
let katex: Katex | null = null
let loading: Promise<void> | null = null
let epoch = 0
const listeners = new Set<() => void>()

function notify() {
  epoch++
  for (const fn of listeners) fn()
}

const subscribe = (fn: () => void) => {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export function setTexEnabled(value: boolean) {
  if (value !== enabled) {
    enabled = value
    notify()
  }
}

function loadKatex() {
  loading ??= Promise.all([import('katex'), import('katex/dist/katex.min.css')])
    .then(([mod]) => {
      katex = mod.default
      notify()
    })
    .catch(() => {
      loading = null // retry on the next render that needs it
    })
}

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
  useSyncExternalStore(subscribe, () => epoch)
  const text = children ?? ''
  if (!enabled || !text.includes('$')) return <>{text}</>
  if (!katex) {
    loadKatex()
    return <>{text}</>
  }
  return <>{toNodes(katex, text, forceInline)}</>
}
