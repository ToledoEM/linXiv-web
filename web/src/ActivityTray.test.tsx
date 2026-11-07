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

  it('dismisses a finished job from its card', async () => {
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

  it('folds finished jobs into a red dot after a few seconds; Dismiss all clears it', async () => {
    vi.useFakeTimers()
    try {
      const jobs = vi.spyOn(api, 'jobs').mockResolvedValue([job({ id: 1 }), job({ id: 2, kind: 'maint-clean-tags' })])
      view()
      await flush()
      jobs.mockResolvedValue([
        job({ id: 1, state: 'done', done: 10 }),
        job({ id: 2, kind: 'maint-clean-tags', state: 'failed', error: 'boom' }),
        job({ id: 3, kind: 'pdf-layout' }), // still running: never folded
      ])
      await act(async () => {
        window.dispatchEvent(new Event('lxw-job-started'))
      })
      expect(screen.getByText('Done')).toBeTruthy()
      expect(screen.queryByRole('button', { name: /finished job/ })).toBeNull()
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000)
      })
      expect(screen.queryByText('Done')).toBeNull()
      const dot = screen.getByRole('button', { name: '2 finished jobs' })
      expect(dot.textContent).toBe('2')
      expect(screen.getByRole('link', { name: 'PDF folders' })).toBeTruthy()
      fireEvent.click(dot)
      expect(screen.getByText('Done')).toBeTruthy()
      expect(screen.getByText('Failed')).toBeTruthy()
      fireEvent.click(screen.getAllByRole('button', { name: 'Dismiss' })[0])
      expect(screen.getByRole('button', { name: '1 finished job' })).toBeTruthy()
      fireEvent.click(screen.getByRole('button', { name: 'Dismiss all' }))
      expect(screen.queryByRole('button', { name: /finished job/ })).toBeNull()
      expect(screen.getByRole('link', { name: 'PDF folders' })).toBeTruthy()
    } finally {
      vi.useRealTimers()
    }
  })

  it('closes the finished list with Escape', async () => {
    vi.useFakeTimers()
    try {
      const jobs = vi.spyOn(api, 'jobs').mockResolvedValue([job({})])
      view()
      await flush()
      jobs.mockResolvedValue([job({ state: 'done', done: 10 })])
      await act(async () => {
        window.dispatchEvent(new Event('lxw-job-started'))
        await vi.advanceTimersByTimeAsync(5_000)
      })
      fireEvent.click(screen.getByRole('button', { name: '1 finished job' }))
      expect(screen.getByRole('region', { name: 'Finished jobs' })).toBeTruthy()
      fireEvent.keyDown(window, { key: 'Escape' })
      expect(screen.queryByRole('region', { name: 'Finished jobs' })).toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })
})
