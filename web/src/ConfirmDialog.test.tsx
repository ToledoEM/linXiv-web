import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConfirmDialog from './ConfirmDialog'

const setup = (props: Partial<Parameters<typeof ConfirmDialog>[0]> = {}) => {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  const view = render(
    <ConfirmDialog open title="Replace library?" phrase="replace library" onConfirm={onConfirm} onCancel={onCancel} {...props}>
      <p>Every paper is replaced.</p>
    </ConfirmDialog>,
  )
  const dialog = view.container.querySelector('dialog') as HTMLDialogElement
  return { onConfirm, onCancel, dialog, ...view }
}

describe('ConfirmDialog', () => {
  it('opens as a modal with its title and text', () => {
    const { dialog } = setup()
    expect(dialog.open).toBe(true)
    expect(screen.getByRole('heading', { name: 'Replace library?' })).toBeTruthy()
    expect(screen.getByText('Every paper is replaced.')).toBeTruthy()
  })

  it('enables confirm only after the exact phrase', () => {
    const { onConfirm } = setup()
    const confirm = screen.getByRole('button', { name: 'Confirm' }) as HTMLButtonElement
    const input = screen.getByRole('textbox')
    expect(confirm.disabled).toBe(true)
    fireEvent.change(input, { target: { value: 'replace librar' } })
    expect(confirm.disabled).toBe(true)
    fireEvent.change(input, { target: { value: 'replace library' } })
    expect(confirm.disabled).toBe(false)
    fireEvent.click(confirm)
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('cancels on Esc, backdrop and Cancel, but not while busy', () => {
    const { dialog, onCancel, rerender } = setup()
    fireEvent(dialog, new Event('cancel', { cancelable: true }))
    fireEvent.click(dialog)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledTimes(3)
    rerender(
      <ConfirmDialog open busy title="t" onConfirm={() => {}} onCancel={onCancel}>
        x
      </ConfirmDialog>,
    )
    fireEvent(dialog, new Event('cancel', { cancelable: true }))
    expect(onCancel).toHaveBeenCalledTimes(3)
    expect((screen.getByRole('button', { name: 'Working…' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('closes when open turns false', () => {
    const { dialog, rerender } = setup()
    rerender(<ConfirmDialog open={false} title="t" onConfirm={() => {}} onCancel={() => {}} />)
    expect(dialog.open).toBe(false)
  })
})
