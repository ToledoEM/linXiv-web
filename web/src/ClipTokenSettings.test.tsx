import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import ClipTokenSettings from './ClipTokenSettings'

describe('ClipTokenSettings', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows a new token once', async () => {
    vi.spyOn(api, 'clipTokenStatus')
      .mockResolvedValueOnce({ set: false, hint: null, created: null })
      .mockResolvedValue({ set: true, hint: 'abcd', created: '2026-11-03T10:00:00Z' })
    vi.spyOn(api, 'clipCreateToken').mockResolvedValue({
      token: 'lxclip_secretabcd',
      hint: 'abcd',
      created: '2026-11-03T10:00:00Z',
    })
    render(<ClipTokenSettings />)
    fireEvent.click(await screen.findByRole('button', { name: 'Create token' }))
    await screen.findByText('lxclip_secretabcd')
    await screen.findByText(/…abcd, created 2026-11-03/)
  })

  it('revokes on the second click', async () => {
    vi.spyOn(api, 'clipTokenStatus').mockResolvedValue({ set: true, hint: 'abcd', created: '2026-11-03T10:00:00Z' })
    const revoke = vi.spyOn(api, 'clipRevokeToken').mockResolvedValue({})
    render(<ClipTokenSettings />)
    fireEvent.click(await screen.findByRole('button', { name: 'Revoke token' }))
    expect(revoke).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Revoke now?' }))
    await waitFor(() => expect(revoke).toHaveBeenCalledTimes(1))
  })
})
