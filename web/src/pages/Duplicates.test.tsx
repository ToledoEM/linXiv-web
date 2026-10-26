import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { DuplicatesReport } from '../types'
import Duplicates from './Duplicates'

const report = (): DuplicatesReport => ({
  scanned_at: '2026-10-26T03:00:00+02:00',
  groups: [
    {
      sha256: 'h1',
      papers: [
        { source_id: 'doi:10.1/a', version: 1, title: 'Paper A', file: 'a.pdf', size: 2048 },
        { source_id: 'local:b', version: 1, title: 'Paper B', file: 'b.pdf', size: 2048 },
        { source_id: 'local:c', version: 1, title: '', file: 'c.pdf', size: 2048 },
      ],
    },
  ],
})

const show = () =>
  render(
    <MemoryRouter>
      <Duplicates />
    </MemoryRouter>,
  )

describe('Duplicates', () => {
  afterEach(() => vi.restoreAllMocks())

  it('merges every other paper into the one kept', async () => {
    vi.spyOn(api, 'duplicates').mockResolvedValue(report())
    const merge = vi.spyOn(api, 'mergeDuplicate').mockResolvedValue({ ...report(), groups: [] })
    show()
    expect(await screen.findByText('Paper A')).toBeTruthy()
    expect(screen.getByText('local:c')).toBeTruthy() // no title: id shown
    fireEvent.click(screen.getByLabelText('Keep local:b'))
    fireEvent.click(screen.getByRole('button', { name: 'Merge into kept paper' }))
    fireEvent.click(screen.getByRole('button', { name: 'Merge' }))
    await waitFor(() => expect(merge).toHaveBeenCalledTimes(2))
    expect(merge.mock.calls).toEqual([
      ['local:b', 'doi:10.1/a'],
      ['local:b', 'local:c'],
    ])
    expect(await screen.findByText('No duplicates found.')).toBeTruthy()
  })

  it('dismisses a group', async () => {
    vi.spyOn(api, 'duplicates').mockResolvedValue(report())
    const dismiss = vi.spyOn(api, 'dismissDuplicates').mockResolvedValue({ ...report(), groups: [] })
    show()
    fireEvent.click(await screen.findByRole('button', { name: 'Not duplicates' }))
    await waitFor(() => expect(dismiss).toHaveBeenCalledWith(['doi:10.1/a', 'local:b', 'local:c']))
  })

  it('says when no scan has run', async () => {
    vi.spyOn(api, 'duplicates').mockResolvedValue({ scanned_at: null, groups: [] })
    show()
    expect(await screen.findByText(/Not checked yet/)).toBeTruthy()
  })
})
