import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import PdfCheckOptions from './PdfCheckOptions'
import PdfCheckReport from './PdfCheckReport'
import type { Job, PdfCheckReport as Report } from './types'

const report = (): Report => ({
  library: 'root',
  checked_at: '2026-10-26T03:00:00',
  pdfs: 12,
  missing_count: 1,
  unlinked_count: 1,
  missing: [{ source_id: 'doi:10.1/gone', version: 1, title: 'Gone paper' }],
  unlinked: [{ file: '2021/stray.pdf', size: 2048 }],
  papers: 11,
  papers_with_pdf: 10,
  extra_versions: 1,
  trashed_pdfs: 0,
  skip: ['dup', 'orphans'],
  disk: {
    files: 15,
    pdf_files: 14,
    other_files: 1,
    skipped_files: 2,
    by_folder: [
      { folder: '.', files: 12, pdfs: 11, unlinked: 0, skipped: false },
      { folder: '2021', files: 1, pdfs: 1, unlinked: 1, skipped: false },
      { folder: 'dup', files: 2, pdfs: 2, unlinked: 0, skipped: true },
    ],
  },
})

const open = (container: HTMLElement) => {
  const details = container.querySelector('details')!
  details.open = true
  fireEvent(details, new Event('toggle'))
}

const job = (patch: Partial<Job>): Job => ({
  id: 7,
  kind: 'pdf-orphans',
  library: 'root',
  state: 'running',
  total: 1,
  done: 0,
  current: null,
  result: {},
  errors: [],
  error: null,
  started_at: 0,
  finished_at: null,
  cancel_requested: false,
  ...patch,
})

describe('PdfCheckReport', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('loads the report when opened, with the disk breakdown', async () => {
    const load = vi.spyOn(api, 'pdfCheck').mockResolvedValue({ libraries: [report()] })
    const { container } = render(<PdfCheckReport />)
    expect(load).not.toHaveBeenCalled()
    open(container)
    expect(await screen.findByText('Gone paper')).toBeTruthy()
    expect(screen.getByText('12 PDFs · 1 missing · 1 unlinked')).toBeTruthy()
    expect(screen.getByText(/2021\/stray\.pdf/)).toBeTruthy()
    expect(screen.getByText(/14 PDFs, 1 other files, 2 in skipped folders \(dup, orphans\)/)).toBeTruthy()
    expect(screen.getByText('dup/')).toBeTruthy()
    expect(screen.getByText('2 PDFs · skipped')).toBeTruthy()
    const links = screen.getAllByText('Download full list (TSV)').map((a) => a.getAttribute('href'))
    expect(links).toEqual([
      '/api/maintenance/pdf-check/root/missing.tsv',
      '/api/maintenance/pdf-check/root/unlinked.tsv',
    ])
  })

  it('moves unlinked files after confirm and shows the result', async () => {
    vi.spyOn(api, 'pdfCheck').mockResolvedValue({ libraries: [report()] })
    const move = vi.spyOn(api, 'moveOrphans').mockResolvedValue(job({}))
    const poll = vi
      .spyOn(api, 'job')
      .mockResolvedValue(job({ state: 'done', done: 1, result: { moved: 1, skipped_recent: 0, failed: 0 } }))
    const { container } = render(<PdfCheckReport />)
    open(container)
    fireEvent.click(await screen.findByRole('button', { name: 'Move unlinked files of root to orphans' }))
    vi.useFakeTimers()
    fireEvent.click(screen.getByRole('button', { name: 'Move', hidden: true }))
    await act(async () => {
      await Promise.resolve()
    })
    expect(move).toHaveBeenCalledWith('root')
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100)
    })
    vi.useRealTimers()
    expect(poll).toHaveBeenCalledWith(7)
    await waitFor(() => expect(screen.getByText(/Moved 1 to orphans\//)).toBeTruthy())
  })
})

describe('PdfCheckOptions', () => {
  afterEach(() => vi.restoreAllMocks())

  it('saves the skip list', async () => {
    vi.spyOn(api, 'pdfCheckOptions').mockResolvedValue({ skip: ['dup'], always: ['orphans'] })
    const save = vi.spyOn(api, 'setPdfCheckOptions').mockResolvedValue({ skip: ['dup', 'errors'], always: ['orphans'] })
    render(<PdfCheckOptions />)
    const input = await screen.findByLabelText('Folders the PDF check skips')
    expect((input as HTMLInputElement).value).toBe('dup')
    fireEvent.change(input, { target: { value: 'dup, errors ,' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    await waitFor(() => expect(save).toHaveBeenCalledWith(['dup', 'errors']))
    expect((input as HTMLInputElement).value).toBe('dup, errors')
  })
})
