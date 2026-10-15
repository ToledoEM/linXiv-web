import { describe, expect, it } from 'vitest'
import { idPath, paperPath } from './api'

describe('paperPath', () => {
  it('keeps ":" and "/" readable', () => {
    expect(paperPath('doi:10.1111/j.1432-1033.1967.tb19495.x')).toBe('/paper/doi:10.1111/j.1432-1033.1967.tb19495.x')
    expect(paperPath('arxiv:hep-th/9901001')).toBe('/paper/arxiv:hep-th/9901001')
  })

  it('still encodes characters that break a path', () => {
    expect(paperPath('doi:10.1/a#b?c%d')).toBe('/paper/doi:10.1/a%23b%3Fc%25d')
  })

  it('leaves API paths encoded', () => {
    expect(idPath('doi:10.1/x')).toBe('doi%3A10.1/x')
  })
})
