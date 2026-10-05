// Store for the `tex_rendering_enabled` setting plus the lazily loaded KaTeX
// module; MathText (tex.tsx) re-renders when either changes. Kept out of
// tex.tsx so that file only exports components (React fast refresh).

export type Katex = typeof import('katex').default

let enabled = true
let katex: Katex | null = null
let loading: Promise<void> | null = null
let epoch = 0
const listeners = new Set<() => void>()

function notify() {
  epoch++
  for (const fn of listeners) fn()
}

export const subscribe = (fn: () => void) => {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export const getEpoch = () => epoch
export const texEnabled = () => enabled
export const loadedKatex = () => katex

export function setTexEnabled(value: boolean) {
  if (value !== enabled) {
    enabled = value
    notify()
  }
}

export function loadKatex() {
  loading ??= Promise.all([import('katex'), import('katex/dist/katex.min.css')])
    .then(([mod]) => {
      katex = mod.default
      notify()
    })
    .catch(() => {
      loading = null // retry on the next render that needs it
    })
}
