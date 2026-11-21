// Accessibility options (Settings → Appearance → Accessibility), kept per browser.
// Each option is off by default so the standard interface stays unchanged.

import { useEffect, useState } from 'react'

export interface A11yPrefs {
  /** Show a "Skip to content" link on the first Tab press. */
  skipLink: boolean
  /** Thicker focus outline everywhere, including controls with a custom cue. */
  focusRing: boolean
  /** Muted text mixed closer to the theme's text colour (AA contrast). */
  contrast: boolean
}

export const DEFAULT_A11Y: A11yPrefs = { skipLink: false, focusRing: false, contrast: false }

const KEY = 'lxw.a11y'
const EVENT = 'lxw-a11y-change'

export function normalizeA11y(value: unknown): A11yPrefs {
  const v = (value && typeof value === 'object' ? value : {}) as Partial<A11yPrefs>
  return { skipLink: v.skipLink === true, focusRing: v.focusRing === true, contrast: v.contrast === true }
}

export function loadA11y(): A11yPrefs {
  try {
    const raw = localStorage.getItem(KEY)
    return raw === null ? DEFAULT_A11Y : normalizeA11y(JSON.parse(raw))
  } catch {
    return DEFAULT_A11Y
  }
}

/** CSS keys off `[data-a11y-focus]` and `[data-a11y-contrast]` on the root. */
export function applyA11y(prefs: A11yPrefs): void {
  const root = document.documentElement
  root.toggleAttribute('data-a11y-focus', prefs.focusRing)
  root.toggleAttribute('data-a11y-contrast', prefs.contrast)
}

export function saveA11y(prefs: A11yPrefs): A11yPrefs {
  const next = normalizeA11y(prefs)
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // storage unavailable: the choice lasts for this page load only
  }
  applyA11y(next)
  window.dispatchEvent(new CustomEvent<A11yPrefs>(EVENT, { detail: next }))
  return next
}

/** Current options, updated when Settings changes them. */
export function useA11y(): A11yPrefs {
  const [prefs, setPrefs] = useState(loadA11y)
  useEffect(() => {
    const handler = (e: Event) => setPrefs((e as CustomEvent<A11yPrefs>).detail)
    window.addEventListener(EVENT, handler)
    return () => window.removeEventListener(EVENT, handler)
  }, [])
  return prefs
}
