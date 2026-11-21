import { beforeEach, describe, expect, it } from 'vitest'
import { DEFAULT_A11Y, loadA11y, normalizeA11y, saveA11y } from './a11y'

describe('a11y prefs', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-a11y-focus')
    document.documentElement.removeAttribute('data-a11y-contrast')
  })

  it('defaults to everything off', () => {
    expect(loadA11y()).toEqual(DEFAULT_A11Y)
    expect(Object.values(DEFAULT_A11Y).every((v) => v === false)).toBe(true)
  })

  it('round-trips through storage', () => {
    const on = { skipLink: true, focusRing: true, contrast: false }
    saveA11y(on)
    expect(loadA11y()).toEqual(on)
  })

  it('sets and clears the root attributes', () => {
    const root = document.documentElement
    saveA11y({ skipLink: false, focusRing: true, contrast: true })
    expect(root.hasAttribute('data-a11y-focus')).toBe(true)
    expect(root.hasAttribute('data-a11y-contrast')).toBe(true)
    saveA11y(DEFAULT_A11Y)
    expect(root.hasAttribute('data-a11y-focus')).toBe(false)
    expect(root.hasAttribute('data-a11y-contrast')).toBe(false)
  })

  it('ignores junk', () => {
    expect(normalizeA11y(null)).toEqual(DEFAULT_A11Y)
    expect(normalizeA11y({ skipLink: 'yes' })).toEqual(DEFAULT_A11Y)
    localStorage.setItem('lxw.a11y', '{not json')
    expect(loadA11y()).toEqual(DEFAULT_A11Y)
  })
})
