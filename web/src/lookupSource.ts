// Default Retrieve metadata source (Settings → Library → Metadata lookup). Read once
// per page load; Settings dispatches `lxw-lookup-source` when it is saved.

import { useEffect, useState } from 'react'
import { api } from './api'
import type { DefaultLookupSource } from './types'

const EVENT = 'lxw-lookup-source'
let cached: Promise<DefaultLookupSource> | null = null

function load(): Promise<DefaultLookupSource> {
  cached ??= api
    .settings()
    .then((r) => r.settings.web_lookup_source || 'auto')
    .catch(() => 'auto' as const)
  return cached
}

export function setLookupSource(source: DefaultLookupSource): void {
  cached = Promise.resolve(source)
  window.dispatchEvent(new CustomEvent<DefaultLookupSource>(EVENT, { detail: source }))
}

/** The default source, or null until it has loaded. */
export function useLookupSource(): DefaultLookupSource | null {
  const [source, setSource] = useState<DefaultLookupSource | null>(null)
  useEffect(() => {
    let live = true
    load().then((v) => live && setSource(v))
    const handler = (e: Event) => setSource((e as CustomEvent<DefaultLookupSource>).detail)
    window.addEventListener(EVENT, handler)
    return () => {
      live = false
      window.removeEventListener(EVENT, handler)
    }
  }, [])
  return source
}
