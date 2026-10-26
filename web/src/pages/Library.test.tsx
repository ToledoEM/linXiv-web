import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Paper } from '../types'
import Library from './Library'

const paper = (sid: string, title: string): Paper =>
  ({ source_id: sid, title, authors: [], tags: [], published: '2020-01-01' }) as unknown as Paper

function Where() {
  return <span data-testid="search">{useLocation().search}</span>
}

const show = (url: string) =>
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route
          path="/library"
          element={
            <>
              <Library />
              <Where />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  )

function mockApi() {
  vi.spyOn(api, 'settings').mockRejectedValue(new Error('offline'))
  vi.spyOn(api, 'allTags').mockResolvedValue([])
  vi.spyOn(api, 'duplicates').mockResolvedValue({ scanned_at: '2026-10-26T03:00:00', groups: [] })
  vi.spyOn(api, 'metadataReview').mockResolvedValue({
    papers: [{ source_id: 'local:x', title: 'scan0001', missing: ['title'] }],
  })
  vi.spyOn(api, 'papers').mockResolvedValue([paper('local:x', 'scan0001'), paper('arxiv:1', 'Attention')])
}

describe('Library metadata review', () => {
  afterEach(() => vi.restoreAllMocks())

  it('links to the papers left incomplete', async () => {
    mockApi()
    show('/library')
    expect(await screen.findByRole('link', { name: '1 to complete' })).toBeTruthy()
  })

  it('?review=metadata selects them and opens batch edit metadata', async () => {
    mockApi()
    show('/library?review=metadata')
    expect(await screen.findByLabelText('Batch edit metadata')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Look up 1 selected' })).toBeTruthy()
    await waitFor(() => expect(screen.getByTestId('search').textContent).toBe(''))
  })
})
