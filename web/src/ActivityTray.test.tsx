import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ActivityTray from './ActivityTray'
import { api } from './api'
import type { Job } from './types'

const job = (o: Partial<Job>): Job => ({
  id: 1,
  kind: 'index-pdf-text',
  state: 'running',
  total: 10,
  done: 3,
  current: 'doi:10.1/x',
  result: {},
  errors: [],
  error: null,
  started_at: 0,
  finished_at: null,
  cancel_requested: false,
  ...o,
})

const view = () =>
  render(
    <MemoryRouter>
      <ActivityTray />
    </MemoryRouter>,
  )

const flush = () => act(async () => {})

describe('ActivityTray', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows nothing when no job runs', async () => {
    vi.spyOn(api, 'jobs').mockResolvedValue([job({ state: 'done' })])
    const { container } = view()
    await flush()
    expect(container.querySelector('.activity-tray')).toBeNull()
  })

  it('shows a running job with progress and cancels it', async () => {
    vi.spyOn(api, 'jobs').mockResolvedValue([job({})])
    const cancel = vi.spyOn(api, 'cancelJob').mockResolvedValue(job({ cancel_requested: true }))
    view()
    await flush()
    expect(screen.getByRole('link', { name: 'PDF text index' }).getAttribute('href')).toBe('/settings#library')
    expect(screen.getByText('3 / 10')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    await flush()
    expect(cancel).toHaveBeenCalledWith(1)
  })

  it('keeps a job that finished while watched until dismissed', async () => {
    const jobs = vi.spyOn(api, 'jobs').mockResolvedValue([job({})])
    view()
    await flush()
    jobs.mockResolvedValue([job({ state: 'done', done: 10 })])
    await act(async () => {
      window.dispatchEvent(new Event('lxw-job-started')) // any wake-up polls again
    })
    expect(screen.getByText('Done')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByText('Done')).toBeNull()
  })
})
