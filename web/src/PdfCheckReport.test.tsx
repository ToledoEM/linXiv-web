import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import PdfCheckReport from './PdfCheckReport'

describe('PdfCheckReport', () => {
  afterEach(() => vi.restoreAllMocks())

  it('loads the report when opened', async () => {
    const load = vi.spyOn(api, 'pdfCheck').mockResolvedValue({
      libraries: [
        {
          library: 'root',
          checked_at: '2026-10-26T03:00:00',
          pdfs: 12,
          missing_count: 1,
          unlinked_count: 1,
          missing: [{ source_id: 'doi:10.1/gone', version: 1, title: 'Gone paper' }],
          unlinked: [{ file: '2021/stray.pdf', size: 2048 }],
        },
      ],
    })
    const { container } = render(<PdfCheckReport />)
    expect(load).not.toHaveBeenCalled()
    const details = container.querySelector('details')!
    details.open = true
    fireEvent(details, new Event('toggle'))
    expect(await screen.findByText('Gone paper')).toBeTruthy()
    expect(screen.getByText('12 PDFs · 1 missing · 1 unlinked')).toBeTruthy()
    expect(screen.getByText(/2021\/stray\.pdf/)).toBeTruthy()
  })
})
