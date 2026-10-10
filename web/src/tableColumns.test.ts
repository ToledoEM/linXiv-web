import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DEFAULT_TABLE_COLUMNS, loadTableColumns, saveTableColumns, tableMinWidth } from './tableColumns'

const KEY = 'lxw.tableColumns'

describe('table columns', () => {
  beforeEach(() => localStorage.clear())

  it('defaults when nothing or junk is stored', () => {
    expect(loadTableColumns()).toEqual(DEFAULT_TABLE_COLUMNS)
    localStorage.setItem(KEY, 'not json')
    expect(loadTableColumns()).toEqual(DEFAULT_TABLE_COLUMNS)
  })

  it('keeps valid stored values and drops invalid ones', () => {
    localStorage.setItem(
      KEY,
      JSON.stringify({
        show: { tags: false, authors: 'no', extra: true },
        width: { authors: 'wide', tags: 'huge' },
        doi: { library: true },
      }),
    )
    const cols = loadTableColumns()
    expect(cols.show).toEqual({ ...DEFAULT_TABLE_COLUMNS.show, tags: false })
    expect(cols.width).toEqual({ ...DEFAULT_TABLE_COLUMNS.width, authors: 'wide' })
    expect(cols.doi.library).toBe(true)
  })

  it('saves and notifies listeners', () => {
    const seen = vi.fn()
    window.addEventListener('lxw-table-columns', seen)
    const next = { ...DEFAULT_TABLE_COLUMNS, show: { ...DEFAULT_TABLE_COLUMNS.show, pdf: false } }
    saveTableColumns(next)
    window.removeEventListener('lxw-table-columns', seen)
    expect(loadTableColumns()).toEqual(next)
    expect(seen).toHaveBeenCalledOnce()
  })

  it('sums shown column widths for the table minimum', () => {
    // check 2.4 + title 18 + authors 14 + published 7.5 + category 12 + tags 14 + pdf 4.5
    expect(tableMinWidth(DEFAULT_TABLE_COLUMNS)).toBe('72.4rem')
    const titleOnly = {
      ...DEFAULT_TABLE_COLUMNS,
      show: { authors: false, published: false, category: false, tags: false, pdf: false },
    }
    expect(tableMinWidth(titleOnly)).toBe('20.4rem')
  })
})
