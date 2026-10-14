import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Pager } from './components'

describe('Pager', () => {
  it('pages forward and back within bounds and changes the page size', () => {
    const onPage = vi.fn()
    const onSize = vi.fn()
    render(<Pager page={1} size={50} total={120} onPage={onPage} onSize={onSize} />)
    expect(screen.getByText('Page 1 of 3')).toBeTruthy()
    expect((screen.getByRole('button', { name: /Prev/ }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: /Next/ }))
    expect(onPage).toHaveBeenCalledWith(2)
    fireEvent.change(screen.getByLabelText('Papers per page'), { target: { value: '100' } })
    expect(onSize).toHaveBeenCalledWith(100)
  })

  it('disables Next on the last page', () => {
    render(<Pager page={3} size={50} total={120} onPage={() => {}} onSize={() => {}} />)
    expect((screen.getByRole('button', { name: /Next/ }) as HTMLButtonElement).disabled).toBe(true)
  })
})
