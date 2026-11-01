import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import RefreshOptions from './RefreshOptions'
import type { RefreshOptions as Options, RefreshScope } from './types'

const opts = (scope: RefreshScope): Options => ({ scope, all_scopes: ['all', 'recent_or_preprint'] })

describe('RefreshOptions', () => {
  afterEach(() => vi.restoreAllMocks())

  it('saves the picked scope', async () => {
    vi.spyOn(api, 'refreshOptions').mockResolvedValue(opts('recent_or_preprint'))
    const save = vi.spyOn(api, 'setRefreshOptions').mockImplementation((s) => Promise.resolve(opts(s)))
    render(<RefreshOptions />)
    const all = await screen.findByLabelText('Every paper with a recorded source')
    expect((all as HTMLInputElement).checked).toBe(false)
    fireEvent.click(all)
    await waitFor(() => expect(save).toHaveBeenCalledWith('all'))
    await waitFor(() => expect((all as HTMLInputElement).checked).toBe(true))
  })

  it('shows a load error', async () => {
    vi.spyOn(api, 'refreshOptions').mockRejectedValue(new Error('nope'))
    render(<RefreshOptions />)
    expect(await screen.findByText('nope')).toBeTruthy()
  })
})
