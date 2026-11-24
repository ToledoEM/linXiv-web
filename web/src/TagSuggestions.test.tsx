import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TagSuggestions from './TagSuggestions'

describe('TagSuggestions', () => {
  it('marks new tags, matched wording and queued aliases', () => {
    const toggle = vi.fn()
    render(
      <TagSuggestions
        suggestions={[
          { tag: 'RNA-seq', known: true, in_vocab: false, how: 'exact', from: 'RNA sequencing' },
          { tag: 'organoid', known: false, in_vocab: true, how: 'exact' },
          { tag: 'neural network', known: true, in_vocab: false, how: 'llm-alias', from: 'neural nets' },
          { tag: 'perceptron', known: false, in_vocab: false, how: 'new' },
        ]}
        picked={new Set(['RNA-seq'])}
        onToggle={toggle}
        dropped={[{ candidate: 'STAT5', reason: 'no close tag' }]}
      />,
    )
    const rna = screen.getByRole('button', { name: /RNA-seq/ })
    expect(rna.textContent).toBe('RNA-seq ← RNA sequencing')
    expect(rna.getAttribute('aria-pressed')).toBe('true')
    expect(rna.getAttribute('title')).toBe(
      'Already used in your library. Same tag in another spelling (model wrote "RNA sequencing")',
    )
    expect(screen.getByRole('button', { name: /organoid/ }).textContent).toBe('organoid')
    expect(screen.getByRole('button', { name: /neural network/ }).textContent).toBe(
      'neural network ← neural nets alias?',
    )
    expect(screen.getByRole('button', { name: /perceptron/ }).textContent).toBe('perceptron new')
    expect(screen.getByText('Left out: STAT5 (no close tag)')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /perceptron/ }))
    expect(toggle).toHaveBeenCalledWith('perceptron')
  })

  it('says so when nothing new is suggested', () => {
    render(<TagSuggestions suggestions={[]} picked={new Set()} onToggle={() => {}} />)
    expect(screen.getByText('No new tags suggested.')).toBeTruthy()
  })
})
