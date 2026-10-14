import { describe, expect, it } from 'vitest'
import { formatBytes, paperJournal, paperLabel } from './format'

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

describe('paperJournal', () => {
  it('uses the category, else the journal reference; arXiv subject codes are not journals', () => {
    expect(paperJournal({ source_id: 'arxiv:1', category: 'cs.CL', journal_ref: null })).toBe('arXiv preprint')
    expect(paperJournal({ source_id: 'arxiv:1', category: 'hep-th', journal_ref: null })).toBe('arXiv preprint')
    expect(paperJournal({ source_id: 'arxiv:1', category: 'cs.CL', journal_ref: 'NeurIPS 2017' })).toBe('NeurIPS 2017')
    expect(paperJournal({ source_id: 'arxiv:1', category: 'Nature', journal_ref: null })).toBe('Nature')
    expect(paperJournal({ source_id: 'doi:10.1/x', category: 'Nature', journal_ref: 'Nat. 1' })).toBe('Nature')
    expect(paperJournal({ source_id: 'local:x', category: ' ', journal_ref: 'J. Ref' })).toBe('J. Ref')
    expect(paperJournal({ source_id: 'local:x', category: null, journal_ref: null })).toBe('')
  })
})
