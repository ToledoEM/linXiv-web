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
    expect(save.mock.calls[0][1]).toMatchObject({
      title: 'New a:1',
      tags: ['keep'],
      metadata_source: { source: 'crossref', ref: 'a:1' },
    })
    expect(save.mock.calls[0][1].bib).toBeUndefined() // none read yet: the server fetches them
    expect(save.mock.calls[0][1].bib_fill_only).toBe(true) // ...and fills empty fields only
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

  const lookupOffline = (match: (sid: string) => 'doi' | 'title') => {
    vi.spyOn(api, 'settings').mockRejectedValue(new Error('offline'))
    vi.spyOn(api, 'paper').mockImplementation((sid: string) => Promise.resolve(paper(sid)))
    return vi
      .spyOn(api, 'lookupMetadata')
      .mockImplementation((sid: string) => Promise.resolve({ match: match(sid), candidates: [found(sid)] }))
  }

  it('offers no Done outside the check workflow', async () => {
    lookupOffline(() => 'doi')
    render(<BatchMetadata selected={['a:1']} titles={{}} onSaved={() => {}} onSkip={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Look up 1 selected' }))
    await screen.findByRole('button', { name: 'Approve' })
    expect(screen.queryByRole('button', { name: 'Done' })).toBeNull()
  })

  it('Done works without approving, and stays after a save', async () => {
    lookupOffline(() => 'doi')
    vi.spyOn(api, 'saveMetadata').mockResolvedValue({} as Paper)
    const onDone = vi.fn().mockResolvedValue(undefined)
    render(<BatchMetadata selected={['a:1']} titles={{}} onSaved={() => {}} onSkip={() => {}} onDone={onDone} />)
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await waitFor(() => expect(onDone).toHaveBeenCalledWith('a:1'))
    fireEvent.click(screen.getByRole('button', { name: 'Look up 1 selected' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Approve' })).toBeNull())
    expect(screen.getByRole('button', { name: 'Done' })).toBeTruthy()
  })

  it('shows why Done failed', async () => {
    vi.spyOn(api, 'settings').mockRejectedValue(new Error('offline'))
    const onDone = vi.fn().mockRejectedValue(new Error('remove failed'))
    render(<BatchMetadata selected={['a:1']} titles={{}} onSaved={() => {}} onSkip={() => {}} onDone={onDone} />)
    fireEvent.click(screen.getByRole('button', { name: 'Done' }))
    await screen.findByText('remove failed')
  })

  it('guard keeps title matches out of Approve all, not single Approve', async () => {
    lookupOffline((sid) => (sid === 'a:2' ? 'title' : 'doi'))
    const save = vi.spyOn(api, 'saveMetadata').mockResolvedValue({} as Paper)
    render(
      <BatchMetadata selected={['a:1', 'a:2']} titles={{}} onSaved={() => {}} onSkip={() => {}} guardTitleMatches />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Look up 2 selected' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Approve all (1)' }))
    screen.getByText(/1 matched by title/)
    fireEvent.click(screen.getByRole('button', { name: 'Save 1 paper now' }))
    await screen.findByText('1 saved.')
    expect(save).toHaveBeenCalledTimes(1)
    expect(save.mock.calls[0][0]).toBe('a:1')
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2))
    expect(save.mock.calls[1][0]).toBe('a:2')
  })

  it('lists BibTeX rows, pre-ticks only empty stored fields, saves the ticked ones', async () => {
    vi.spyOn(api, 'settings').mockRejectedValue(new Error('offline'))
    vi.spyOn(api, 'paper').mockResolvedValue({ ...paper('a:1'), bib: { volume: '9' } } as Paper)
    vi.spyOn(api, 'lookupMetadata').mockResolvedValue({
      match: 'doi',
      candidates: [{ ...found('a:1'), title: 'Old a:1', bib: { volume: '521', pages: '436--444' } }],
    })
    const save = vi.spyOn(api, 'saveMetadata').mockResolvedValue({} as Paper)
    render(<BatchMetadata selected={['a:1']} titles={{}} onSaved={() => {}} onSkip={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Look up 1 selected' }))
    const pages = await screen.findByRole('checkbox', { name: 'Use found Pages (BibTeX) for a:1' })
    const volume = screen.getByRole('checkbox', { name: 'Use found Volume (BibTeX) for a:1' })
    expect((pages as HTMLInputElement).checked).toBe(true)
    expect((volume as HTMLInputElement).checked).toBe(false) // stored value kept unless ticked
    // only BibTeX differs: still approvable
    fireEvent.click(screen.getByRole('button', { name: 'Approve' }))
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
    expect(save.mock.calls[0][1].bib).toEqual({ pages: '436--444' })
    expect(save.mock.calls[0][1].bib_fill_only).toBeUndefined()
  })

  it('agrees when the BibTeX fields match too', async () => {
    vi.spyOn(api, 'settings').mockRejectedValue(new Error('offline'))
    vi.spyOn(api, 'paper').mockResolvedValue({ ...paper('a:1'), bib: { volume: '9' } } as Paper)
    vi.spyOn(api, 'lookupMetadata').mockResolvedValue({
      match: 'doi',
      candidates: [{ ...found('a:1'), title: 'Old a:1', bib: { volume: '9' } }],
    })
    render(<BatchMetadata selected={['a:1']} titles={{}} onSaved={() => {}} onSkip={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'Look up 1 selected' }))
    await screen.findByText('Agrees with the current metadata.')
    expect((screen.getByRole('button', { name: 'Approve' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('defaultSource wins over the Settings default', async () => {
    const lookup = lookupOffline(() => 'doi')
    render(
      <BatchMetadata selected={['a:1']} titles={{}} onSaved={() => {}} onSkip={() => {}} defaultSource="crossref" />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Look up 1 selected' }))
    await waitFor(() => expect(lookup).toHaveBeenCalled())
    expect(lookup.mock.calls[0][1]).toBe('crossref')
  })
})
