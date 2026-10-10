import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { NoteMarkdown } from './NoteMarkdown'
import { extractMath, restoreMath } from './noteMath'

describe('noteMath', () => {
  it('swaps math for placeholders and back, leaving code alone', () => {
    const raw = 'See $a_b * c_d$ and `$not math$` then $$x^2$$ costs $5 and $6'
    const { text, math } = extractMath(raw)
    expect(math).toEqual(['$a_b * c_d$', '$$x^2$$'])
    expect(text).toContain('`$not math$`')
    expect(text).not.toContain('a_b')
    expect(restoreMath(text, math)).toBe(raw)
  })

  it('leaves real digits alone when restoring', () => {
    expect(restoreMath('room 12', ['$x$'])).toBe('room 12')
  })
})

describe('NoteMarkdown', () => {
  it('renders Markdown blocks and inline styles', () => {
    const { container } = render(<NoteMarkdown content={'# Key idea\n\n- **bold** item\n- [link](https://example.org)'} />)
    expect(container.querySelector('h1')?.textContent).toBe('Key idea')
    expect(container.querySelector('li strong')?.textContent).toBe('bold')
    expect(container.querySelector('a')?.getAttribute('href')).toBe('https://example.org')
  })

  it('keeps TeX intact instead of turning _ and * into emphasis', () => {
    const { container } = render(<NoteMarkdown content={'Uses $a_b * c_d$ here.'} />)
    expect(container.querySelector('em')).toBeNull()
    expect(container.textContent).toContain('a_b * c_d')
  })

  it('does not render raw HTML or javascript: links', () => {
    const { container } = render(<NoteMarkdown content={'<img src=x onerror=alert(1)> [x](javascript:alert(1))'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('a')?.getAttribute('href') ?? '').not.toContain('javascript')
  })
})
