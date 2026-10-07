// Whether AI features are switched on (Settings → AI). Read once per page load;
// Settings dispatches `lxw-ai-enabled` when the switch is saved.

import { useEffect, useState } from 'react'
import { api } from './api'

const EVENT = 'lxw-ai-enabled'
let cached: Promise<boolean> | null = null

function load(): Promise<boolean> {
  cached ??= api
    .settings()
    .then((r) => r.settings.ai_enabled)
    .catch(() => false)
  return cached
}

export function setAiEnabled(on: boolean): void {
  cached = Promise.resolve(on)
  window.dispatchEvent(new CustomEvent<boolean>(EVENT, { detail: on }))
}

export function useAiEnabled(): boolean {
  const [on, setOn] = useState(false)
  useEffect(() => {
    let live = true
    load().then((v) => live && setOn(v))
    const handler = (e: Event) => setOn((e as CustomEvent<boolean>).detail)
    window.addEventListener(EVENT, handler)
    return () => {
      live = false
      window.removeEventListener(EVENT, handler)
    }
  }, [])
  return on
}
