import { describe, expect, it } from 'vitest'
import { parseDisabled } from './lookupSource'
import { autoSource, initialSource, sourcesFor, toMetadataInput } from './metadataFields'
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

describe('toMetadataInput', () => {
  const form = {
    title: 'A paper',
    authors: '',
    published: '2024-01-02',
    summary: '',
    category: '',
    doi: '',
    url: '',
  }

  it('accepts a paper with no authors (the server fills in a placeholder)', () => {
    const r = toMetadataInput(form)
    expect(r).toEqual({ input: expect.objectContaining({ authors: [] }) })
  })

  it('still requires a title and a date', () => {
    expect(toMetadataInput({ ...form, title: '  ' })).toHaveProperty('error')
    expect(toMetadataInput({ ...form, published: '2024-1-2' })).toHaveProperty('error')
    expect(toMetadataInput({ ...form, doi: '10.12/x' })).toHaveProperty('error')
    expect(toMetadataInput({ ...form, doi: 'DOI: 10.1038/nature14539.' })).toMatchObject({
      input: { doi: '10.1038/nature14539' },
    })
  })
})

describe('initialSource', () => {
  it('uses the default unless it is switched off', () => {
    expect(initialSource(other, { source: 'pubmed', disabled: new Set() })).toBe('pubmed')
    expect(initialSource(arxiv, { source: 'pubmed', disabled: parseDisabled('pubmed') })).toBe('arxiv')
    expect(initialSource(arxiv, null)).toBe('arxiv')
  })
})
