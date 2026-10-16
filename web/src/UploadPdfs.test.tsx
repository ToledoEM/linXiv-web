import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import UploadPdfs from './UploadPdfs'

const pdf = (name: string, size = 10) => new File(['x'.repeat(size)], name, { type: 'application/pdf' })
const drop = (files: File[]) =>
  fireEvent.drop(screen.getByTestId('drop-zone'), { dataTransfer: { files, types: ['Files'] } })

const view = () =>
  render(
    <MemoryRouter>
      <UploadPdfs />
    </MemoryRouter>,
  )

describe('UploadPdfs drop zone', () => {
  afterEach(() => vi.restoreAllMocks())

  it('keeps dropped PDFs, skips other files, ignores repeats', () => {
    view()
    drop([pdf('a.pdf'), new File(['t'], 'notes.txt', { type: 'text/plain' }), pdf('B.PDF')])
    expect(screen.getByText('2 PDFs selected')).toBeTruthy()
    expect(screen.getByText('1 file skipped: not a PDF.')).toBeTruthy()
    drop([pdf('a.pdf')])
    expect(screen.getByText('2 PDFs selected')).toBeTruthy()
  })

  it('imports the selection one by one and lists results', async () => {
    const spy = vi
      .spyOn(api, 'importPdf')
      .mockResolvedValueOnce({ source_id: 'doi:10.1/a', title: 'Paper A' } as never)
      .mockRejectedValueOnce(new Error('not a PDF'))
    view()
    drop([pdf('a.pdf'), pdf('b.pdf')])
    fireEvent.click(screen.getByRole('button', { name: 'Upload' }))
    await waitFor(() => expect(screen.getByText('not a PDF')).toBeTruthy())
    expect(spy).toHaveBeenCalledTimes(2)
    expect(screen.getByRole('link', { name: 'Paper A' })).toBeTruthy()
    expect(screen.queryByText(/selected/)).toBeNull()
  })
})
