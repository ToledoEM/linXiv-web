// Which optional pages the sidebar shows (desktop Settings → Sidebar, ui store
// `sidebarPages`). Home, Library, Projects, Authors and Settings always show.
// Kept per browser; a hidden page's route redirects to Home.

import { useEffect, useState } from 'react'

export type PageKey = 'reading' | 'tags' | 'graph' | 'search' | 'add' | 'duplicates' | 'trash'
export type SidebarPages = Record<PageKey, boolean>

export const PAGE_OPTIONS: { key: PageKey; route: string; label: string; description: string }[] = [
  { key: 'reading', route: '/reading', label: 'Reading lists', description: 'Papers queued to read' },
  { key: 'tags', route: '/tags', label: 'Tags', description: 'Tags and how many papers carry each' },
  { key: 'graph', route: '/graph', label: 'Graph', description: 'Knowledge graph of papers, authors and tags' },
  { key: 'search', route: '/search', label: 'Search', description: 'arXiv / OpenAlex / Crossref search' },
  {
    key: 'add',
    route: '/add',
    label: 'Add Paper',
    description: 'Add papers by link, DOI or arXiv ID, upload PDFs, import metadata files',
  },
  { key: 'duplicates', route: '/duplicates', label: 'Duplicates', description: 'Papers that share the same PDF file' },
  { key: 'trash', route: '/trash', label: 'Trash', description: 'Deleted papers and projects' },
]

export const DEFAULT_SIDEBAR_PAGES: SidebarPages = {
  reading: true,
  tags: true,
  graph: true,
  search: true,
  add: true,
  duplicates: true,
  trash: true,
}

const KEY = 'lxw.sidebarPages'
const EVENT = 'lxw-sidebar-pages'

export function loadSidebarPages(): SidebarPages {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, unknown>
    const out = { ...DEFAULT_SIDEBAR_PAGES }
    for (const k of Object.keys(out) as PageKey[]) if (typeof raw[k] === 'boolean') out[k] = raw[k] as boolean
    return out
  } catch {
    return { ...DEFAULT_SIDEBAR_PAGES }
  }
}

export function setSidebarPage(key: PageKey, visible: boolean): void {
  const next = { ...loadSidebarPages(), [key]: visible }
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // storage unavailable: the choice lasts for this page load only
  }
  window.dispatchEvent(new CustomEvent<SidebarPages>(EVENT, { detail: next }))
}

/** Live view of the toggles: the sidebar and the Settings card stay in step. */
export function useSidebarPages(): SidebarPages {
  const [pages, setPages] = useState(loadSidebarPages)
  useEffect(() => {
    const handler = (e: Event) => setPages((e as CustomEvent<SidebarPages>).detail)
    window.addEventListener(EVENT, handler)
    return () => window.removeEventListener(EVENT, handler)
  }, [])
  return pages
}

/** The hidden optional page `pathname` belongs to, if any. */
export function hiddenPageFor(pathname: string, pages: SidebarPages): PageKey | null {
  const hit = PAGE_OPTIONS.find((o) => pathname === o.route || pathname.startsWith(o.route + '/'))
  return hit && !pages[hit.key] ? hit.key : null
}
