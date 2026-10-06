// Keyboard shortcuts (desktop src/lib/shortcuts.ts): the inventory Settings lists,
// plus the one window listener that dispatches the global ones. In a browser,
// Ctrl/Cmd+F and "/" are only claimed while a PDF reader is open, so the
// browser's own find keeps working everywhere else.

import { useEffect } from 'react'
import { DEFAULT_ZOOM, loadZoom, saveZoom, ZOOM_STEP } from './display'
import { PDF_FIND_EVENT } from './pdfFind'

export interface Shortcut {
  id: string
  /** Key tokens rendered as separate <kbd> chips. */
  keys: string[]
  description: string
  scope: 'global' | 'form'
  match?: (e: KeyboardEvent) => boolean
  run?: () => void
  /** Only claim the key when this says so (e.g. a PDF reader is open). */
  available?: () => boolean
  /** Skip while an input/textarea/select/contenteditable has focus. */
  skipWhenTyping?: boolean
}

let openReaders = 0
/** PdfReader registers while mounted; the find shortcuts are live only then. */
export function registerPdfReader(): () => void {
  openReaders += 1
  return () => {
    openReaders -= 1
  }
}
const readerOpen = () => openReaders > 0

export function isTypingTarget(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null
  if (!el || !el.tagName) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || !!el.isContentEditable
}

const openPdfFind = () => window.dispatchEvent(new Event(PDF_FIND_EVENT))
// Ctrl (Win/Linux) or Cmd (macOS), but not Alt.
const mod = (e: KeyboardEvent) => (e.ctrlKey || e.metaKey) && !e.altKey

export const SHORTCUTS: Shortcut[] = [
  {
    id: 'zoom-in',
    keys: ['Ctrl/Cmd', '+'],
    description: 'Zoom the interface in',
    scope: 'global',
    match: (e) => mod(e) && (e.key === '+' || e.key === '='),
    run: () => saveZoom(loadZoom() + ZOOM_STEP),
  },
  {
    id: 'zoom-out',
    keys: ['Ctrl/Cmd', '-'],
    description: 'Zoom the interface out',
    scope: 'global',
    match: (e) => mod(e) && (e.key === '-' || e.key === '_'),
    run: () => saveZoom(loadZoom() - ZOOM_STEP),
  },
  {
    id: 'zoom-reset',
    keys: ['Ctrl/Cmd', '0'],
    description: 'Reset the interface zoom to 100%',
    scope: 'global',
    match: (e) => mod(e) && e.key === '0',
    run: () => saveZoom(DEFAULT_ZOOM),
  },
  {
    id: 'pdf-find',
    keys: ['Ctrl/Cmd', 'F'],
    description: 'Find text in the open PDF (the browser’s find elsewhere)',
    scope: 'global',
    match: (e) => mod(e) && e.key.toLowerCase() === 'f',
    run: openPdfFind,
    available: readerOpen,
  },
  {
    id: 'pdf-find-slash',
    keys: ['/'],
    description: 'Find text in the open PDF (quick key)',
    scope: 'global',
    match: (e) => !e.ctrlKey && !e.metaKey && !e.altKey && e.key === '/',
    run: openPdfFind,
    available: readerOpen,
    skipWhenTyping: true,
  },
  {
    id: 'submit',
    keys: ['Ctrl/Cmd', 'Enter'],
    description: 'Save the focused form or editor',
    scope: 'form',
  },
]

/** One window keydown listener for the global shortcuts. Mount once, near the root. */
export function useGlobalShortcuts(): void {
  useEffect(() => {
    // Holding a shortcut keeps firing it (continuous zoom), but only for a
    // combo whose first keydown this listener saw.
    const open = new Set<string>()
    const combo = (e: KeyboardEvent) => `${e.ctrlKey || e.metaKey}${e.altKey}${e.shiftKey}:${e.key.toLowerCase()}`
    const onKeyDown = (e: KeyboardEvent) => {
      const c = combo(e)
      if (e.repeat) {
        if (!open.has(c)) return
      } else {
        open.add(c)
      }
      for (const s of SHORTCUTS) {
        if (!s.run || !s.match?.(e)) continue
        if (s.available && !s.available()) continue
        if (s.skipWhenTyping && isTypingTarget(e.target)) continue
        e.preventDefault()
        s.run()
        return
      }
    }
    const onKeyUp = (e: KeyboardEvent) => open.delete(combo(e))
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [])
}
