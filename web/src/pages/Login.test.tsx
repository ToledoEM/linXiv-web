import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from '../api'
import Login from './Login'

describe('Login', () => {
  afterEach(() => vi.restoreAllMocks())

  it('single-user: password only', async () => {
    const spy = vi.spyOn(api, 'login').mockResolvedValue({} as never)
    const onLogin = vi.fn()
    render(<Login onLogin={onLogin} />)
    expect(screen.queryByLabelText('Username')).toBeNull()
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret-pw' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    await waitFor(() => expect(onLogin).toHaveBeenCalled())
    expect(spy).toHaveBeenCalledWith('secret-pw', false, undefined)
  })

  it('multi-user: asks for a username and sends it trimmed', async () => {
    const spy = vi.spyOn(api, 'login').mockResolvedValue({} as never)
    render(<Login multiUser onLogin={vi.fn()} />)
    const button = screen.getByRole('button', { name: 'Log in' })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret-pw' } })
    expect((button as HTMLButtonElement).disabled).toBe(true)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: ' alice ' } })
    fireEvent.click(button)
    await waitFor(() => expect(spy).toHaveBeenCalledWith('secret-pw', false, 'alice'))
  })

  it('shows the server error', async () => {
    vi.spyOn(api, 'login').mockRejectedValue(new Error('invalid username or password'))
    render(<Login multiUser onLogin={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'bob' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'nope-nope' } })
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect(await screen.findByText('invalid username or password')).toBeTruthy()
  })
})
