import { describe, expect, it } from 'vitest'
import { parseDisabled } from './lookupSource'
import { autoSource, initialSource, sourcesFor } from './metadataFields'
import type { Paper } from './types'

const arxiv = { source_id: 'arxiv:2401.00001' } as Paper
const biorxiv = { source_id: 'doi:10.1101/x', doi: '10.1101/x' } as Paper
const other = { source_id: 'local:abc', doi: null } as Paper

describe('sourcesFor', () => {
  it('hides switched-off sources and AI while AI is off', () => {
    const prefs = { source: 'pubmed' as const, disabled: parseDisabled('arxiv,ai') }
    expect(sourcesFor(true, prefs).map((s) => s.value)).toEqual(['pubmed', 'crossref', 'openalex', 'biorxiv'])
    expect(sourcesFor(false).map((s) => s.value)).toEqual(['crossref', 'arxiv', 'openalex', 'pubmed', 'biorxiv'])
  })
})

describe('autoSource', () => {
  it('picks by id or DOI', () => {
    expect(autoSource(arxiv)).toBe('arxiv')
    expect(autoSource(biorxiv)).toBe('biorxiv')
    expect(autoSource(other)).toBe('crossref')
    expect(autoSource(null)).toBe('crossref')
  })

  it('falls back to the first source still on', () => {
    expect(autoSource(arxiv, parseDisabled('arxiv'))).toBe('crossref')
    expect(autoSource(other, parseDisabled('crossref,arxiv'))).toBe('openalex')
  })
})

describe('initialSource', () => {
  it('uses the default unless it is switched off', () => {
    expect(initialSource(other, { source: 'pubmed', disabled: new Set() })).toBe('pubmed')
    expect(initialSource(arxiv, { source: 'pubmed', disabled: parseDisabled('pubmed') })).toBe('arxiv')
    expect(initialSource(arxiv, null)).toBe('arxiv')
  })
})
