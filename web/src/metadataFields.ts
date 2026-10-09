// Metadata form model shared by the single-paper editor (MetadataEditor) and
// the Library batch edit panel (BatchMetadata).

import type { LookupSource, MetadataCandidate, MetadataInput, Paper } from './types'

export type Form = {
  title: string
  authors: string // one per line
  published: string
  summary: string
  category: string
  doi: string
  url: string
}
export type Field = keyof Form

export const FIELDS: { key: Field; label: string }[] = [
  { key: 'title', label: 'Title' },
  { key: 'authors', label: 'Authors' },
  { key: 'published', label: 'Published' },
  { key: 'category', label: 'Journal / category' },
  { key: 'doi', label: 'DOI' },
  { key: 'url', label: 'URL' },
  { key: 'summary', label: 'Abstract' },
]

export const SOURCES: { value: LookupSource; label: string }[] = [
  { value: 'crossref', label: 'Crossref' },
  { value: 'arxiv', label: 'arXiv' },
  { value: 'openalex', label: 'OpenAlex' },
  { value: 'pubmed', label: 'PubMed' },
  { value: 'biorxiv', label: 'bioRxiv / medRxiv' },
  { value: 'ai', label: 'AI cleanup (title, authors, journal)' },
]

/** Sources that can search by the title in the PDF's file name (bioRxiv has no title search). */
export const byFileNameOk = (s: LookupSource) => s !== 'biorxiv' && s !== 'ai'

/** Lookup sources to offer: AI cleanup only while AI features are on. */
export const sourcesFor = (aiOn: boolean) => SOURCES.filter((s) => aiOn || s.value !== 'ai')

export const MATCH_LABEL = {
  doi: 'by DOI',
  arxiv: 'by arXiv id',
  title: 'by title',
  filename: 'by PDF file name',
  ai: 'from AI cleanup',
}
export type MatchKind = keyof typeof MATCH_LABEL

export function fromPaper(p: Paper): Form {
  return {
    title: p.title ?? '',
    authors: (p.authors ?? []).join('\n'),
    published: p.published ?? '',
    summary: p.summary ?? '',
    category: p.category ?? '',
    doi: p.doi ?? '',
    url: p.url ?? '',
  }
}

export function fromCandidate(c: MetadataCandidate): Form {
  return {
    title: c.title ?? '',
    authors: c.authors.join('\n'),
    published: c.published ?? '',
    summary: c.summary ?? '',
    category: c.category ?? '',
    doi: c.doi ?? '',
    url: c.url ?? '',
  }
}

export const norm = (s: string) => s.trim().replace(/\s+/g, ' ')

/** Fields where the found value differs from the current one. */
export const diffFields = (current: Form, found: Form) => FIELDS.filter((f) => norm(found[f.key]) !== norm(current[f.key]))

/** Pre-ticked differences: only where the source has a value (a blank would erase data). */
export const defaultPicked = (current: Form, found: Form) =>
  new Set(diffFields(current, found).filter((f) => found[f.key].trim()).map((f) => f.key))

/** Validated save body, or the reason it can't be saved (same rules as the editor). */
export function toMetadataInput(form: Form): { input: MetadataInput } | { error: string } {
  const authors = form.authors
    .split('\n')
    .map((a) => a.trim())
    .filter(Boolean)
  if (!form.title.trim()) return { error: 'Title is required.' }
  if (!authors.length) return { error: 'At least one author is required.' }
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.published)) return { error: 'Published must be a date (YYYY-MM-DD).' }
  return {
    input: {
      title: form.title.trim(),
      authors,
      published: form.published,
      summary: form.summary,
      category: form.category.trim() || null,
      doi: form.doi.trim() || null,
      url: form.url.trim() || null,
    },
  }
}
