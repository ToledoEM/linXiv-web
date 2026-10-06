// Interface zoom and density (desktop src/lib/zoom.ts + density.ts), kept per browser.

export const MIN_ZOOM = 0.5
export const MAX_ZOOM = 2.0
export const ZOOM_STEP = 0.1
export const DEFAULT_ZOOM = 1.0

export type Density = 'comfortable' | 'compact'
export const DEFAULT_DENSITY: Density = 'comfortable'

const ZOOM_KEY = 'lxw.zoom'
const DENSITY_KEY = 'lxw.density'

/** Clamp to the range and round to whole percent: repeated ±0.1 steps drift otherwise. */
export function clampZoom(zoom: number): number {
  if (!Number.isFinite(zoom)) return DEFAULT_ZOOM
  return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(zoom * 100) / 100))
}

export function normalizeDensity(value: unknown): Density {
  return value === 'compact' ? 'compact' : DEFAULT_DENSITY
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value)
  } catch {
    // storage unavailable: the choice lasts for this page load only
  }
}

export const loadZoom = (): number => {
  const raw = read(ZOOM_KEY)
  return raw === null ? DEFAULT_ZOOM : clampZoom(Number(raw))
}
export const loadDensity = (): Density => normalizeDensity(read(DENSITY_KEY))

/** CSS `zoom` on the root scales the whole interface (the desktop browser path). */
export function applyZoom(zoom: number): void {
  const factor = clampZoom(zoom)
  document.documentElement.style.setProperty('zoom', String(factor))
  // Viewport-height layouts (sticky sidebar) divide by this to stay one screen tall.
  document.documentElement.style.setProperty('--zoom', String(factor))
}

/** Density CSS keys off `[data-density]` on the root. */
export function applyDensity(density: Density): void {
  document.documentElement.dataset.density = normalizeDensity(density)
}

const ZOOM_EVENT = 'lxw-zoom-change'

export function saveZoom(zoom: number): number {
  const next = clampZoom(zoom)
  write(ZOOM_KEY, String(next))
  applyZoom(next)
  window.dispatchEvent(new CustomEvent<number>(ZOOM_EVENT, { detail: next }))
  return next
}

/** Keeps zoom readouts (Settings) and canvas resolution (PDF reader) in step with key zooms. */
export function onZoomChange(fn: (zoom: number) => void): () => void {
  const handler = (e: Event) => fn((e as CustomEvent<number>).detail)
  window.addEventListener(ZOOM_EVENT, handler)
  return () => window.removeEventListener(ZOOM_EVENT, handler)
}

export function saveDensity(density: Density): Density {
  const next = normalizeDensity(density)
  write(DENSITY_KEY, next)
  applyDensity(next)
  return next
}
