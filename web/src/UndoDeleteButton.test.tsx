import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { UndoDeleteButton } from './projectParts'

const setup = () => {
  const onConfirm = vi.fn()
  const view = render(<UndoDeleteButton label="Delete paper" busy={false} onConfirm={onConfirm} />)
  return { onConfirm, ...view }
}

describe('UndoDeleteButton', () => {
  it('first press shows Undo first and the delete button beside it, deleting nothing', () => {
    vi.useFakeTimers()
    const { onConfirm, container } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Delete paper' }))
    const buttons = [...container.querySelectorAll('button')].map((b) => b.textContent)
    expect(buttons).toEqual(['Undo', 'Delete paper'])
    vi.advanceTimersByTime(60_000)
    expect(onConfirm).not.toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('Undo returns to the single delete button', () => {
    const { onConfirm, container } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Delete paper' }))
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect([...container.querySelectorAll('button')].map((b) => b.textContent)).toEqual(['Delete paper'])
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('second delete press confirms once', () => {
    const { onConfirm } = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Delete paper' }))
    fireEvent.click(screen.getByRole('button', { name: 'Delete paper' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })
})
