import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'
import type { UserAccount } from './types'
import UsersPanel from './UsersPanel'

const owner: UserAccount = {
  id: 1,
  username: 'boss',
  role: 'admin',
  library: 'root',
  created_at: '2026-10-22T10:00:00+00:00',
  owner: true,
}
const alice: UserAccount = { ...owner, id: 2, username: 'alice', role: 'user', library: 'u2', owner: false }

describe('UsersPanel', () => {
  afterEach(() => vi.restoreAllMocks())

  it('lists accounts; the owner keeps admin and has no delete', async () => {
    vi.spyOn(api, 'users').mockResolvedValue([owner, alice])
    render(<UsersPanel selfName="boss" />)
    expect(await screen.findByText('alice')).toBeTruthy()
    expect((screen.getByLabelText('Role of boss') as HTMLSelectElement).disabled).toBe(true)
    expect((screen.getByLabelText('Role of alice') as HTMLSelectElement).disabled).toBe(false)
    expect(screen.getAllByRole('button', { name: 'Delete' })).toHaveLength(1)
  })

  it('adds a user with a lowercase name', async () => {
    vi.spyOn(api, 'users').mockResolvedValue([owner])
    const create = vi.spyOn(api, 'createUser').mockResolvedValue(alice)
    render(<UsersPanel selfName="boss" />)
    await screen.findByText('boss')
    const add = screen.getByRole('button', { name: 'Add user' })
    fireEvent.change(screen.getByLabelText(/^Username/), { target: { value: 'Alice' } })
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'short' } })
    expect((add as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText(/^Password/), { target: { value: 'alice-password' } })
    fireEvent.click(add)
    await waitFor(() =>
      expect(create).toHaveBeenCalledWith({ username: 'alice', password: 'alice-password', role: 'user' }),
    )
    expect(await screen.findByText(/Account alice created/)).toBeTruthy()
  })

  it('deletes after confirming and reports the kept library', async () => {
    vi.spyOn(api, 'users').mockResolvedValue([owner, alice])
    const del = vi.spyOn(api, 'deleteUser').mockResolvedValue({ ok: true, library_dir: '/data/libraries/u2' })
    render(<UsersPanel selfName="boss" />)
    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete account' }))
    await waitFor(() => expect(del).toHaveBeenCalledWith(2))
    expect(await screen.findByText(/stays on disk: \/data\/libraries\/u2/)).toBeTruthy()
  })

  it('shows server errors', async () => {
    vi.spyOn(api, 'users').mockResolvedValue([owner, alice])
    vi.spyOn(api, 'updateUser').mockRejectedValue(new Error('cannot demote the last admin'))
    render(<UsersPanel selfName="boss" />)
    fireEvent.change(await screen.findByLabelText('Role of alice'), { target: { value: 'admin' } })
    expect(await screen.findByText('cannot demote the last admin')).toBeTruthy()
  })
})
