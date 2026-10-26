import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import BatchMetadata from './BatchMetadata'
import type { MetadataCandidate, Paper } from './types'

const paper = (sid: string): Paper =>
  ({
    source_id: sid,
    title: `Old ${sid}`,
    authors: ['A. Person'],
    published: '2020-01-01',
    summary: '',
    category: null,
    doi: null,
    url: null,
    tags: ['keep'],
  }) as unknown as Paper

const found = (sid: string): MetadataCandidate => ({
  source: 'crossref',
  ref: sid,
  title: `New ${sid}`,
  authors: ['A. Person'],
  published: '2020-01-01',
  summary: null,
  category: null,
  doi: null,
  url: null,
})

describe('BatchMetadata', () => {
  afterEach(() => vi.restoreAllMocks())

  it('Approve all reloads once and sends the loaded tags', async () => {
    vi.spyOn(api, 'settings').mockRejectedValue(new Error('offline'))
    vi.spyOn(api, 'paper').mockImplementation((sid: string) => Promise.resolve(paper(sid)))
    vi.spyOn(api, 'lookupMetadata').mockImplementation((sid: string) =>
      Promise.resolve({ match: 'doi', candidates: [found(sid)] }),
    )
    const save = vi.spyOn(api, 'saveMetadata').mockResolvedValue({} as Paper)
    const onSaved = vi.fn()
    render(<BatchMetadata selected={['a:1', 'a:2']} titles={{}} onSaved={onSaved} onSkip={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Look up 2 selected' }))
    const all = await screen.findByRole('button', { name: 'Approve all (2)' })
    fireEvent.click(all)
    fireEvent.click(screen.getByRole('button', { name: 'Save 2 papers now' }))
    await screen.findByText('2 saved.')
    expect(save).toHaveBeenCalledTimes(2)
    expect(save.mock.calls[0][1]).toMatchObject({ title: 'New a:1', tags: ['keep'] })
    expect(onSaved).toHaveBeenCalledTimes(1)
  })

  it('single Approve reloads after its save', async () => {
    vi.spyOn(api, 'settings').mockRejectedValue(new Error('offline'))
    vi.spyOn(api, 'paper').mockImplementation((sid: string) => Promise.resolve(paper(sid)))
    vi.spyOn(api, 'lookupMetadata').mockImplementation((sid: string) =>
      Promise.resolve({ match: 'doi', candidates: [found(sid)] }),
    )
    vi.spyOn(api, 'saveMetadata').mockResolvedValue({} as Paper)
    const onSaved = vi.fn()
    render(<BatchMetadata selected={['a:1']} titles={{}} onSaved={onSaved} onSkip={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Look up 1 selected' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1))
  })
})
