// Click-to-sort paper tables (Library, project / reading-list detail).
// Sorting is client-side over the loaded rows; the chosen column is kept per
// browser.

import type { Paper } from './types'

export type PaperSortKey = 'title' | 'authors' | 'published' | 'category' | 'tags' | 'pdf'
export type SortDir = 'asc' | 'desc'
export interface PaperSort {
  key: PaperSortKey
  dir: SortDir
}

export const SORT_KEYS: PaperSortKey[] = ['title', 'authors', 'published', 'category', 'tags', 'pdf']

/** Direction a column starts in when first clicked: dates and PDFs newest/has first. */
export function firstDir(key: PaperSortKey): SortDir {
  return key === 'published' || key === 'pdf' ? 'desc' : 'asc'
}

/** Clicking the active column flips it; a new column starts at its natural order. */
export function nextSort(current: PaperSort | null, key: PaperSortKey): PaperSort {
  return current?.key === key ? { key, dir: current.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: firstDir(key) }
}

function value(p: Paper, key: PaperSortKey): string {
  switch (key) {
    case 'title':
      return p.title ?? ''
    case 'authors':
      return p.authors?.[0] ?? ''
    case 'published':
      return p.published ?? ''
    case 'category':
      return p.category ?? ''
    case 'tags':
      return (p.tags ?? []).join(', ')
    case 'pdf':
      return p.has_pdf ? '1' : ''
  }
}

/** Stable sorted copy; empty values go last in both directions. */
export function sortPapers(papers: Paper[], sort: PaperSort | null): Paper[] {
  if (!sort) return papers
  const dir = sort.dir === 'asc' ? 1 : -1
  return papers
    .map((p, i) => ({ p, i, v: value(p, sort.key).trim() }))
    .sort((a, b) => {
      if (!a.v !== !b.v) return a.v ? -1 : 1
      const c = a.v.localeCompare(b.v, undefined, { sensitivity: 'base', numeric: true }) * dir
      return c !== 0 ? c : a.i - b.i
    })
    .map((x) => x.p)
}

export function loadSort<T>(storageKey: string, parse: (raw: unknown) => T, fallback: T): T {
  try {
    const raw = localStorage.getItem(storageKey)
    return raw === null ? fallback : parse(JSON.parse(raw))
  } catch {
    return fallback
  }
}

export function saveSort(storageKey: string, value: unknown): void {
  try {
    localStorage.setItem(storageKey, JSON.stringify(value))
  } catch {
    // storage unavailable: the choice lasts for this page load only
  }
}

/** A stored `{key, dir}` if valid, else null. */
export function parsePaperSort(raw: unknown): PaperSort | null {
  if (!raw || typeof raw !== 'object') return null
  const { key, dir } = raw as Record<string, unknown>
  return SORT_KEYS.includes(key as PaperSortKey) && (dir === 'asc' || dir === 'desc')
    ? { key: key as PaperSortKey, dir }
    : null
}
