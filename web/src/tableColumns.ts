// Paper table layout (Library, project and reading-list pages): which optional
// columns show, how wide they are, and whether a DOI line sits under the title.
// Kept per browser (Settings → Appearance → Paper tables); Title always shows
// and takes the space the other columns leave.

import { useEffect, useState } from 'react'

export type ColumnKey = 'authors' | 'published' | 'category' | 'tags' | 'pdf'
export type WidthKey = 'authors' | 'category' | 'tags'
export type ColumnWidth = 'narrow' | 'normal' | 'wide'
export type DoiPlace = 'library' | 'projects' | 'reading'

export interface TableColumns {
  show: Record<ColumnKey, boolean>
  width: Record<WidthKey, ColumnWidth>
  doi: Record<DoiPlace, boolean>
}

export const COLUMN_OPTIONS: { key: ColumnKey; label: string }[] = [
  { key: 'authors', label: 'Authors' },
  { key: 'published', label: 'Published' },
  { key: 'category', label: 'Category' },
  { key: 'tags', label: 'Tags' },
  { key: 'pdf', label: 'PDF' },
]

export const WIDTH_OPTIONS: { key: WidthKey; label: string }[] = [
  { key: 'authors', label: 'Authors' },
  { key: 'category', label: 'Category' },
  { key: 'tags', label: 'Tags' },
]

export const DOI_OPTIONS: { key: DoiPlace; label: string }[] = [
  { key: 'library', label: 'Library' },
  { key: 'projects', label: 'Projects' },
  { key: 'reading', label: 'Reading lists' },
]

export const WIDTHS: ColumnWidth[] = ['narrow', 'normal', 'wide']

export const DEFAULT_TABLE_COLUMNS: TableColumns = {
  show: { authors: true, published: true, category: true, tags: true, pdf: true },
  width: { authors: 'normal', category: 'normal', tags: 'normal' },
  doi: { library: false, projects: false, reading: false },
}

const KEY = 'lxw.tableColumns'
const EVENT = 'lxw-table-columns'

function merge<T extends Record<string, unknown>>(base: T, raw: unknown, ok: (v: unknown) => boolean): T {
  const out = { ...base }
  if (raw && typeof raw === 'object') {
    for (const k of Object.keys(out)) {
      const v = (raw as Record<string, unknown>)[k]
      if (ok(v)) (out as Record<string, unknown>)[k] = v
    }
  }
  return out
}

export function loadTableColumns(): TableColumns {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? '{}') as Partial<Record<keyof TableColumns, unknown>>
    const isBool = (v: unknown) => typeof v === 'boolean'
    return {
      show: merge(DEFAULT_TABLE_COLUMNS.show, raw.show, isBool),
      width: merge(DEFAULT_TABLE_COLUMNS.width, raw.width, (v) => WIDTHS.includes(v as ColumnWidth)),
      doi: merge(DEFAULT_TABLE_COLUMNS.doi, raw.doi, isBool),
    }
  } catch {
    return structuredClone(DEFAULT_TABLE_COLUMNS)
  }
}

export function saveTableColumns(next: TableColumns): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(next))
  } catch {
    // storage unavailable: the choice lasts for this page load only
  }
  window.dispatchEvent(new CustomEvent<TableColumns>(EVENT, { detail: next }))
}

/** Live view of the layout: tables and the Settings card stay in step. */
export function useTableColumns(): TableColumns {
  const [cols, setCols] = useState(loadTableColumns)
  useEffect(() => {
    const handler = (e: Event) => setCols((e as CustomEvent<TableColumns>).detail)
    window.addEventListener(EVENT, handler)
    return () => window.removeEventListener(EVENT, handler)
  }, [])
  return cols
}

/** Class for a sized column's `<col>`: `col-authors-wide` etc. */
export const colClass = (cols: TableColumns, key: WidthKey) => `col-${key}-${cols.width[key]}`
