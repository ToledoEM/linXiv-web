import { afterEach, describe, expect, it } from 'vitest'
import { setAccount } from './account'
import { libraryHeaders, libraryView, setLibraryView, withLibrary } from './library'

const single = { multiUser: false, username: null, role: 'admin' as const, owner: true }
const user = { multiUser: true, username: 'alice', role: 'user' as const, owner: false }
const admin = { multiUser: true, username: 'boss', role: 'admin' as const, owner: true }

describe('library view', () => {
  afterEach(() => {
    setLibraryView('mine')
    setAccount(single)
  })

  it('is always "mine" in single-user mode', () => {
    setAccount(single)
    setLibraryView('shared')
    expect(libraryView()).toBe('mine')
    expect(libraryHeaders('/api/papers')).toEqual({})
    expect(withLibrary('/api/papers/x/pdf')).toBe('/api/papers/x/pdf')
  })

  it('sends the header and link parameter in the shared view', () => {
    setAccount(user)
    setLibraryView('shared')
    expect(libraryHeaders('/api/papers')).toEqual({ 'X-Linxiv-Library': 'shared' })
    expect(withLibrary('/api/papers/x/pdf')).toBe('/api/papers/x/pdf?library=shared')
    expect(withLibrary('/api/projects/1/export?format=bibtex')).toBe(
      '/api/projects/1/export?format=bibtex&library=shared',
    )
    expect(localStorage.getItem('lxw.library')).toBe('shared')
  })

  it("keeps account routes and a user's own settings out of the shared library", () => {
    setAccount(user)
    setLibraryView('shared')
    for (const url of ['/api/me', '/api/login', '/api/password', '/api/settings']) {
      expect(libraryHeaders(url)).toEqual({})
    }
    setAccount(admin)
    expect(libraryHeaders('/api/settings')).toEqual({ 'X-Linxiv-Library': 'shared' })
  })
})
