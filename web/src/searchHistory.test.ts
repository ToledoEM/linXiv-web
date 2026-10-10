import { beforeEach, describe, expect, it, vi } from 'vitest'
import { addTerm, clearHistory, historySize, suggestions } from './searchHistory'

describe('search history', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.useRealTimers()
  })

  it('ignores blank terms and trims the rest', () => {
    addTerm('   ')
    addTerm('  attention  ')
    expect(historySize()).toBe(1)
    expect(suggestions('att')).toEqual(['attention'])
  })

  it('matches prefixes case-insensitively, ranked by use count', () => {
    addTerm('Transformer')
    addTerm('transfer learning')
    addTerm('transfer learning')
    expect(suggestions('TRANS')).toEqual(['transfer learning', 'Transformer'])
    expect(suggestions('former')).toEqual([])
    expect(suggestions(' ')).toEqual([])
  })

  it('prunes to the most recently used terms', () => {
    vi.useFakeTimers()
    for (const [i, t] of ['a1', 'a2', 'a3'].entries()) {
      vi.setSystemTime(1000 + i)
      addTerm(t, 2)
    }
    expect(suggestions('a')).toEqual(['a3', 'a2'])
  })

  it('clears', () => {
    addTerm('x')
    clearHistory()
    expect(historySize()).toBe(0)
  })

  it('survives junk in storage', () => {
    localStorage.setItem('lxw.searchHistory', '[{"term":1},{"term":"ok","count":1,"last":1}]')
    expect(suggestions('o')).toEqual(['ok'])
    localStorage.setItem('lxw.searchHistory', '{bad')
    expect(historySize()).toBe(0)
  })
})
