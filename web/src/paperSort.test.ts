import { beforeEach, describe, expect, it } from 'vitest'
import { firstDir, loadSort, nextSort, parsePaperSort, saveSort, sortPapers } from './paperSort'
import type { Paper } from './types'

const paper = (o: Partial<Paper>) => ({ source_id: 'x', ...o }) as Paper

describe('nextSort', () => {
  it('starts dates and PDFs descending, text ascending', () => {
    expect(firstDir('published')).toBe('desc')
    expect(firstDir('pdf')).toBe('desc')
    expect(firstDir('title')).toBe('asc')
  })

  it('flips the active column, resets a new one', () => {
    expect(nextSort(null, 'title')).toEqual({ key: 'title', dir: 'asc' })
    expect(nextSort({ key: 'title', dir: 'asc' }, 'title')).toEqual({ key: 'title', dir: 'desc' })
    expect(nextSort({ key: 'title', dir: 'desc' }, 'published')).toEqual({ key: 'published', dir: 'desc' })
  })
})

describe('sortPapers', () => {
  const rows = [
    paper({ source_id: 'a', title: 'Paper 10' }),
    paper({ source_id: 'b', title: '' }),
    paper({ source_id: 'c', title: 'paper 2' }),
    paper({ source_id: 'd', title: 'Paper 2' }),
  ]
  const ids = (ps: Paper[]) => ps.map((p) => p.source_id)

  it('returns the input when unsorted', () => {
    expect(sortPapers(rows, null)).toBe(rows)
  })

  it('sorts numerically, case-insensitively and stably, empties last', () => {
    expect(ids(sortPapers(rows, { key: 'title', dir: 'asc' }))).toEqual(['c', 'd', 'a', 'b'])
  })

  it('keeps empties last when descending', () => {
    expect(ids(sortPapers(rows, { key: 'title', dir: 'desc' }))).toEqual(['a', 'c', 'd', 'b'])
  })

  it('sorts by first author, tags and PDF presence', () => {
    const ps = [
      paper({ source_id: 'a', authors: ['Zed'], tags: ['b'], has_pdf: false }),
      paper({ source_id: 'b', authors: ['Amy', 'Zed'], tags: ['a', 'z'], has_pdf: true }),
    ]
    expect(ids(sortPapers(ps, { key: 'authors', dir: 'asc' }))).toEqual(['b', 'a'])
    expect(ids(sortPapers(ps, { key: 'tags', dir: 'asc' }))).toEqual(['b', 'a'])
    expect(ids(sortPapers(ps, { key: 'pdf', dir: 'desc' }))).toEqual(['b', 'a'])
  })

  it('does not mutate the input', () => {
    const copy = [...rows]
    sortPapers(rows, { key: 'title', dir: 'asc' })
    expect(rows).toEqual(copy)
  })
})

describe('stored sort', () => {
  beforeEach(() => localStorage.clear())

  it('accepts only known keys and directions', () => {
    expect(parsePaperSort({ key: 'title', dir: 'desc' })).toEqual({ key: 'title', dir: 'desc' })
    expect(parsePaperSort({ key: 'nope', dir: 'asc' })).toBeNull()
    expect(parsePaperSort({ key: 'title', dir: 'up' })).toBeNull()
    expect(parsePaperSort('title')).toBeNull()
  })

  it('round-trips through localStorage, falls back on missing or bad JSON', () => {
    expect(loadSort('k', parsePaperSort, null)).toBeNull()
    saveSort('k', { key: 'pdf', dir: 'asc' })
    expect(loadSort('k', parsePaperSort, null)).toEqual({ key: 'pdf', dir: 'asc' })
    localStorage.setItem('k', '{bad')
    expect(loadSort('k', parsePaperSort, null)).toBeNull()
  })
})
