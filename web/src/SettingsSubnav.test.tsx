import { act, fireEvent, render, screen } from '@testing-library/react'
import { useRef, useState } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { sectionSlug, splitSettingsHash } from './settingsHash'
import SettingsSubnav from './SettingsSubnav'

function Page({ titles, section = null }: { titles: string[]; section?: string | null }) {
  const panel = useRef<HTMLDivElement>(null)
  const [cards, setCards] = useState(titles)
  return (
    <MemoryRouter>
      <SettingsSubnav group="server" panel={panel} section={section} />
      <button type="button" onClick={() => setCards((c) => [...c, 'Logs'])}>
        add card
      </button>
      <div ref={panel}>
        {cards.map((t) => (
          <div key={t} className="card settings-section">
            <h3>{t}</h3>
            <div className="card settings-section-inner">
              <h3>Nested, not a card title</h3>
            </div>
          </div>
        ))}
      </div>
    </MemoryRouter>
  )
}

describe('SettingsSubnav', () => {
  const scroll = vi.fn()
  beforeEach(() => {
    Element.prototype.scrollIntoView = scroll
  })
  afterEach(() => scroll.mockReset())

  it('lists the cards of the panel and scrolls to one on click', async () => {
    render(<Page titles={['Storage', 'Login', 'Contacts & API keys']} />)
    const nav = await screen.findByRole('list', { name: 'Sections' })
    const items = [...nav.querySelectorAll('button')].map((b) => b.textContent)
    expect(items).toEqual(['Storage', 'Login', 'Contacts & API keys'])
    expect(document.getElementById('server-contacts-and-api-keys')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Login' }))
    expect(scroll).toHaveBeenCalledTimes(1)
    expect(scroll.mock.contexts[0]).toBe(document.getElementById('server-login'))
    expect(screen.getByRole('button', { name: 'Login' }).getAttribute('aria-current')).toBe('location')
  })

  it('adds a card that renders later', async () => {
    render(<Page titles={['Storage', 'Login']} />)
    await screen.findByRole('list', { name: 'Sections' })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'add card' }))
    })
    expect(screen.getByRole('button', { name: 'Logs' })).toBeTruthy()
  })

  it('shows nothing for a group with one card', () => {
    render(<Page titles={['About']} />)
    expect(screen.queryByRole('list', { name: 'Sections' })).toBeNull()
  })

  it('scrolls to the section named in the hash', async () => {
    render(<Page titles={['Storage', 'Backup']} section="backup" />)
    await screen.findByRole('list', { name: 'Sections' })
    expect(scroll.mock.contexts[0]).toBe(document.getElementById('server-backup'))
  })
})

describe('settings hash', () => {
  it('splits group and section', () => {
    expect(splitSettingsHash('#server/backup')).toEqual({ group: 'server', section: 'backup' })
    expect(splitSettingsHash('#server')).toEqual({ group: 'server', section: null })
    expect(splitSettingsHash('')).toEqual({ group: '', section: null })
    expect(splitSettingsHash('#server/%E0')).toEqual({ group: 'server', section: '%E0' })
  })

  it('slugs card titles', () => {
    expect(sectionSlug('Contacts & API keys')).toBe('contacts-and-api-keys')
    expect(sectionSlug('  PDF full text ')).toBe('pdf-full-text')
  })
})
