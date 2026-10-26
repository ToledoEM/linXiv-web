import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import { runSummary } from './maintenance'
import MaintenanceSettings from './MaintenanceSettings'
import type { Job, MaintenanceOverview } from './types'

const overview = (): MaintenanceOverview => ({
  hour: 3,
  nightly: ['dup'],
  timezone: 'UTC',
  nightly_on: null,
  keep_backups: 7,
  trash_days: 0,
  ops: [
    {
      id: 'dup',
      label: 'Find duplicates',
      description: 'Hashes PDFs.',
      destructive: false,
      last: {
        started_at: '2026-10-26T03:00:00+00:00',
        finished_at: '2026-10-26T03:02:00+00:00',
        state: 'done',
        errors: 1,
        libraries: { root: { groups: 2 }, u2: { groups: 1 }, shared: { error: 'boom' } },
      },
      job: null,
    },
    { id: 'clean', label: 'Clean up', description: 'Deletes old files.', destructive: true, last: null, job: null },
  ],
})

describe('runSummary', () => {
  it('adds numbers over libraries and lists failures', () => {
    expect(runSummary(overview().ops[0].last!)).toBe('3 groups · failed in shared: boom')
    expect(
      runSummary({ started_at: '', finished_at: '', state: 'done', errors: 0, libraries: { root: {} } }),
    ).toBe('nothing to report')
  })
})

describe('MaintenanceSettings', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows the last run and runs an operation', async () => {
    vi.spyOn(api, 'maintenance').mockResolvedValue(overview())
    const run = vi.spyOn(api, 'runMaintenance').mockResolvedValue({} as Job)
    render(<MaintenanceSettings />)
    expect(await screen.findByText(/Last run 2026-10-26 03:02: 3 groups/)).toBeTruthy()
    expect(screen.getByText('Never run')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Run Find duplicates' }))
    await waitFor(() => expect(run).toHaveBeenCalledWith('dup'))
  })

  it('asks before a destructive operation', async () => {
    vi.spyOn(api, 'maintenance').mockResolvedValue(overview())
    const run = vi.spyOn(api, 'runMaintenance').mockResolvedValue({} as Job)
    render(<MaintenanceSettings />)
    fireEvent.click(await screen.findByRole('button', { name: 'Run Clean up' }))
    expect(run).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Run' }))
    await waitFor(() => expect(run).toHaveBeenCalledWith('clean'))
  })

  it('saves the nightly schedule', async () => {
    vi.spyOn(api, 'maintenance').mockResolvedValue(overview())
    const save = vi
      .spyOn(api, 'setMaintenanceSchedule')
      .mockImplementation((body) => Promise.resolve({ keep_backups: 7, trash_days: 0, ...body }))
    render(<MaintenanceSettings />)
    fireEvent.click(await screen.findByLabelText('Run Clean up nightly'))
    await waitFor(() => expect(save).toHaveBeenCalledWith({ hour: 3, nightly: ['dup', 'clean'] }))
    fireEvent.change(screen.getByLabelText('Nightly hour'), { target: { value: '1' } })
    await waitFor(() => expect(save).toHaveBeenLastCalledWith({ hour: 1, nightly: ['dup', 'clean'] }))
  })

  it('lists server backups, keeps a count and deletes one', async () => {
    const data = overview()
    data.ops.push({
      id: 'backup',
      label: 'Back up databases',
      description: 'Copies.',
      destructive: false,
      last: null,
      job: null,
    })
    vi.spyOn(api, 'maintenance').mockResolvedValue(data)
    const b = { library: 'root', name: 'papers-20261026-030000.db', size: 4096 }
    vi.spyOn(api, 'maintenanceBackups').mockResolvedValue({ backups: [b] })
    const del = vi.spyOn(api, 'deleteMaintenanceBackup').mockResolvedValue({ ok: true })
    const save = vi
      .spyOn(api, 'setMaintenanceSchedule')
      .mockImplementation((body) => Promise.resolve({ keep_backups: 7, trash_days: 0, ...body }))
    render(<MaintenanceSettings />)
    expect(await screen.findByText('2026-10-26 03:00:00')).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Download' }).getAttribute('href')).toBe(
      '/api/maintenance/backups/root/papers-20261026-030000.db',
    )
    const keep = screen.getByLabelText('Backups to keep')
    fireEvent.change(keep, { target: { value: '3' } })
    fireEvent.blur(keep)
    await waitFor(() => expect(save).toHaveBeenCalledWith({ hour: 3, nightly: ['dup'], keep_backups: 3 }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' }).at(-1)!)
    await waitFor(() => expect(del).toHaveBeenCalledWith(b))
    expect(await screen.findByText('None yet.')).toBeTruthy()
  })

  it('saves the trash age on the cleanup row', async () => {
    const data = overview()
    data.ops.push({
      id: 'cleanup',
      label: 'Clean up',
      description: 'Deletes.',
      destructive: true,
      last: null,
      job: null,
    })
    vi.spyOn(api, 'maintenance').mockResolvedValue(data)
    const save = vi
      .spyOn(api, 'setMaintenanceSchedule')
      .mockImplementation((body) => Promise.resolve({ keep_backups: 7, trash_days: 0, ...body }))
    render(<MaintenanceSettings />)
    const days = await screen.findByLabelText('Trash days')
    fireEvent.change(days, { target: { value: '-1' } })
    fireEvent.blur(days)
    expect(save).not.toHaveBeenCalled()
    expect((days as HTMLInputElement).value).toBe('0')
    fireEvent.change(days, { target: { value: '30' } })
    fireEvent.blur(days)
    await waitFor(() => expect(save).toHaveBeenCalledWith({ hour: 3, nightly: ['dup'], trash_days: 30 }))
  })
})
