import { describe, expect, it } from 'vitest'
import { formatBytes, paperLabel } from './format'

describe('paperLabel', () => {
  it('prefers title, then PDF file name, then id', () => {
    expect(paperLabel({ source_id: 'id', title: ' T ', pdf_file: 'f.pdf' })).toBe('T')
    expect(paperLabel({ source_id: 'id', title: '  ', pdf_file: 'f.pdf' })).toBe('f.pdf')
    expect(paperLabel({ source_id: 'id', title: '', pdf_file: null })).toBe('id')
  })
})

describe('formatBytes', () => {
  it('uses B, KB and MB', () => {
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1536)).toBe('1.5 KB')
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })
})
