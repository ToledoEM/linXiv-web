// Which library the app shows (multi-user mode): the caller's own or the shared
// one. Kept per browser (`lxw.library`); always "mine" in single-user mode.
// API calls carry `X-Linxiv-Library: shared`, plain links `?library=shared`.

import { useEffect, useState } from 'react'
import { getAccount, useAccount } from './account'

export type LibraryView = 'mine' | 'shared'

const KEY = 'lxw.library'
const EVENT = 'lxw-library'
export const LIBRARY_HEADER = 'X-Linxiv-Library'
// Account routes are never about a library.
const ACCOUNT_ROUTES = [
  '/api/me',
  '/api/login',
  '/api/logout',
  '/api/password',
  '/api/sessions',
  '/api/setup',
  '/api/users',
  '/api/admin',
  '/api/health',
]

function load(): LibraryView {
  try {
    return localStorage.getItem(KEY) === 'shared' ? 'shared' : 'mine'
  } catch {
    return 'mine'
  }
}

let current: LibraryView = load()

export function libraryView(): LibraryView {
  return getAccount().multiUser ? current : 'mine'
}

export function setLibraryView(view: LibraryView): void {
  current = view
  try {
    localStorage.setItem(KEY, view)
  } catch {
    // storage unavailable: keep in-memory state only
  }
  window.dispatchEvent(new CustomEvent<LibraryView>(EVENT, { detail: view }))
}

/** Headers for an API call to `url` in the current view. A user's own settings
 *  (AI keys, contacts) stay theirs while browsing the shared library. */
export function libraryHeaders(url: string): Record<string, string> {
  if (libraryView() !== 'shared') return {}
  if (ACCOUNT_ROUTES.some((p) => url.startsWith(p))) return {}
  if (url.startsWith('/api/settings') && getAccount().role !== 'admin') return {}
  return { [LIBRARY_HEADER]: 'shared' }
}

/** A plain link (PDF viewer, download) in the current view. */
export function withLibrary(url: string): string {
  if (libraryView() !== 'shared') return url
  return `${url}${url.includes('?') ? '&' : '?'}library=shared`
}

export interface LibraryState {
  view: LibraryView
  shared: boolean
  /** Admins change the shared library; everyone changes their own. */
  canWrite: boolean
}

export function useLibrary(): LibraryState {
  const account = useAccount()
  const [view, setView] = useState(current)
  useEffect(() => {
    const handler = (e: Event) => setView((e as CustomEvent<LibraryView>).detail)
    window.addEventListener(EVENT, handler)
    return () => window.removeEventListener(EVENT, handler)
  }, [])
  const shown: LibraryView = account.multiUser ? view : 'mine'
  return { view: shown, shared: shown === 'shared', canWrite: shown !== 'shared' || account.role === 'admin' }
}
