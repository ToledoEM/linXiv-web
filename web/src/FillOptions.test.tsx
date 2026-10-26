import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import FillOptions from './FillOptions'
import type { FillOptions as Options } from './types'

const ALL_GAPS = ['title', 'authors', 'date', 'abstract', 'journal', 'doi']
const ALL_SOURCES = ['arxiv', 'biorxiv', 'crossref', 'pubmed']
const opts = (gaps: string[], sources: string[]): Options => ({
  gaps,
  sources,
  all_gaps: ALL_GAPS,
  all_sources: ALL_SOURCES,
})

describe('FillOptions', () => {
  afterEach(() => vi.restoreAllMocks())

  it('saves gap and source ticks and the source order', async () => {
    vi.spyOn(api, 'fillOptions').mockResolvedValue(opts(ALL_GAPS, ['crossref', 'pubmed']))
    const save = vi
      .spyOn(api, 'setFillOptions')
      .mockImplementation((gaps, sources) => Promise.resolve(opts(gaps, sources)))
    render(<FillOptions />)
    fireEvent.click(await screen.findByLabelText('No abstract'))
    await waitFor(() => expect(save).toHaveBeenLastCalledWith(['title', 'authors', 'date', 'journal', 'doi'], ['crossref', 'pubmed']))
    fireEvent.click(await screen.findByRole('button', { name: 'Move pubmed up' }))
    await waitFor(() =>
      expect(save).toHaveBeenLastCalledWith(['title', 'authors', 'date', 'journal', 'doi'], ['pubmed', 'crossref']),
    )
    fireEvent.click(screen.getByLabelText('arXiv (arXiv papers, by arXiv id)'))
    await waitFor(() =>
      expect(save).toHaveBeenLastCalledWith(
        ['title', 'authors', 'date', 'journal', 'doi'],
        ['pubmed', 'crossref', 'arxiv'],
      ),
    )
  })

  it('keeps at least one gap and one source ticked', async () => {
    vi.spyOn(api, 'fillOptions').mockResolvedValue(opts(['doi'], ['crossref']))
    render(<FillOptions />)
    expect(((await screen.findByLabelText('No DOI')) as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByLabelText('Crossref (any DOI)') as HTMLInputElement).disabled).toBe(true)
    expect((screen.getByLabelText('PubMed (any DOI)') as HTMLInputElement).disabled).toBe(false)
  })
})
