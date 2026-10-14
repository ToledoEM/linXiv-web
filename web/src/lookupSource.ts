// Retrieve metadata preferences (Settings → Library → Metadata lookup): the default
// source and the sources switched off. Read once per page load; Settings dispatches
// `lxw-lookup-source` when they are saved.

import { useEffect, useState } from 'react'
import { api } from './api'
import type { DefaultLookupSource, LookupSource } from './types'

export interface LookupPrefs {
  source: DefaultLookupSource
  disabled: ReadonlySet<LookupSource>
}

const EVENT = 'lxw-lookup-source'
const ALL_ON: LookupPrefs = { source: 'auto', disabled: new Set() }
let cached: Promise<LookupPrefs> | null = null

/** The stored comma list ("pubmed,ai") as a set. */
export function parseDisabled(raw: string | null | undefined): Set<LookupSource> {
  return new Set((raw ?? '').split(',').filter(Boolean) as LookupSource[])
}

function load(): Promise<LookupPrefs> {
  cached ??= api
    .settings()
    .then((r) => ({
      source: r.settings.web_lookup_source || 'auto',
      disabled: parseDisabled(r.settings.web_lookup_disabled),
    }))
    .catch(() => ALL_ON)
  return cached
}

export function setLookupPrefs(source: DefaultLookupSource, disabled: string): void {
  const prefs: LookupPrefs = { source, disabled: parseDisabled(disabled) }
  cached = Promise.resolve(prefs)
  window.dispatchEvent(new CustomEvent<LookupPrefs>(EVENT, { detail: prefs }))
}

/** The lookup preferences, or null until they have loaded. */
export function useLookupPrefs(): LookupPrefs | null {
  const [prefs, setPrefs] = useState<LookupPrefs | null>(null)
  useEffect(() => {
    let live = true
    void load().then((v) => live && setPrefs(v))
    const handler = (e: Event) => setPrefs((e as CustomEvent<LookupPrefs>).detail)
    window.addEventListener(EVENT, handler)
    return () => {
      live = false
      window.removeEventListener(EVENT, handler)
    }
  }, [])
  return prefs
}
