import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import AddPaper from './AddPaper'

describe('Add paper page', () => {
  it('has link, PDF upload and metadata file sections, each with its own button', () => {
    render(
      <MemoryRouter>
        <AddPaper />
      </MemoryRouter>,
    )
    const headings = screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)
    expect(headings).toEqual(['Add by link or identifier', 'Upload PDF files', 'Import a metadata file (no PDFs)'])
    for (const name of ['Add', 'Upload', 'Import']) expect(screen.getByRole('button', { name })).toBeTruthy()
    expect(screen.getByTestId('drop-zone')).toBeTruthy()
  })
})
