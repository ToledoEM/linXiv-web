import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import type { Paper, Project } from '../types'
import ProjectDetail from './ProjectDetail'

const project = {
  id: 7,
  name: 'Imported - to check',
  description: '',
  color_hex: null,
  project_tags: ['reading-list'],
  source_ids: ['a:1', 'a:2'],
  paper_count: 2,
  status: 'active',
  created_at: '',
  updated_at: '',
  archived_at: null,
  share_id: null,
} as Project

const paper = (sid: string): Paper =>
  ({ source_id: sid, title: `T ${sid}`, authors: [], tags: [], published: '2020-01-01' }) as unknown as Paper

const show = (clipList: number | null) => {
  vi.spyOn(api, 'settings').mockRejectedValue(new Error('offline'))
  vi.spyOn(api, 'project').mockResolvedValue(project)
  const papers = vi.spyOn(api, 'projectPapers').mockResolvedValue([paper('a:1'), paper('a:2')])
  vi.spyOn(api, 'clipList').mockResolvedValue({ project_id: clipList })
  render(
    <MemoryRouter initialEntries={['/projects/7']}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetail />} />
      </Routes>
    </MemoryRouter>,
  )
  return papers
}

describe('ProjectDetail check workflow', () => {
  afterEach(() => vi.restoreAllMocks())

  it('other projects get no Check metadata button', async () => {
    show(99)
    await screen.findByRole('button', { name: 'batch edit' })
    await waitFor(() => expect(api.clipList).toHaveBeenCalled())
    expect(screen.queryByRole('button', { name: 'Check metadata' })).toBeNull()
  })

  it('Check metadata selects every paper, Done takes one off the list', async () => {
    const papers = show(7)
    const remove = vi.spyOn(api, 'removeProjectPaper').mockResolvedValue({})
    fireEvent.click(await screen.findByRole('button', { name: 'Check metadata' }))
    await screen.findByRole('button', { name: 'Look up 2 selected' })
    papers.mockClear()
    fireEvent.click(screen.getAllByRole('button', { name: 'Done' })[0])
    await waitFor(() => expect(remove).toHaveBeenCalledWith(7, 'a:1'))
    await waitFor(() => expect(papers).toHaveBeenCalled())
    await screen.findByRole('button', { name: 'Look up 1 selected' })
  })
})
