// Metadata form model shared by the single-paper editor (MetadataEditor) and
// the Library batch edit panel (BatchMetadata).

import { cleanDoi, isValidDoi } from './format'
import type { LookupPrefs } from './lookupSource'
import type {
  BibFields,
  BibKey,
  DefaultLookupSource,
  LookupSource,
  MetadataCandidate,
  MetadataInput,
  MetadataSource,
  Paper,
} from './types'

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

/** Lookup sources to offer: the ones not switched off in Settings, AI cleanup only
 * while AI features are on; a fixed default from Settings at the top ("auto" keeps
 * the usual order). */
export function sourcesFor(aiOn: boolean, prefs?: LookupPrefs | null) {
  const first = prefs?.source
  const list = SOURCES.filter((s) => (aiOn || s.value !== 'ai') && !prefs?.disabled.has(s.value))
  return [...list.filter((s) => s.value === first), ...list.filter((s) => s.value !== first)]
}

/** "Auto": arXiv papers use arXiv, bioRxiv/medRxiv DOIs (10.1101/…, bioRxiv's newer
 * 10.64898/…) their own API, everything else (and a batch) Crossref. A pick that is
 * switched off falls back to the first source still on. */
export function autoSource(
  paper: Paper | null,
  disabled: ReadonlySet<LookupSource> = new Set(),
): Exclude<LookupSource, 'ai'> {
  let pick: Exclude<LookupSource, 'ai'> = 'crossref'
  if (paper?.source_id.startsWith('arxiv:')) pick = 'arxiv'
  else if (/^10\.(1101|64898)\//.test(cleanDoi(paper?.doi))) pick = 'biorxiv'
  if (!disabled.has(pick)) return pick
  const on = SOURCES.find((s) => s.value !== 'ai' && !disabled.has(s.value))
  return (on?.value ?? pick) as Exclude<LookupSource, 'ai'>
}

/** Source preselected for `paper` (null = batch): the Settings default, or `autoSource`. */
export function initialSource(paper: Paper | null, prefs: LookupPrefs | null): LookupSource {
  const def: DefaultLookupSource = prefs?.source ?? 'auto'
  const disabled = prefs?.disabled ?? new Set<LookupSource>()
  return def === 'auto' || disabled.has(def) ? autoSource(paper, disabled) : def
}

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
  // Authors may be empty: the server fills in a placeholder, since `paper repair` requires the flag.
  if (!/^\d{4}-\d{2}-\d{2}$/.test(form.published)) return { error: 'Published must be a date (YYYY-MM-DD).' }
  const doi = cleanDoi(form.doi)
  if (doi && !isValidDoi(doi)) return { error: `DOI "${doi}" is not a valid DOI.` }
  return {
    input: {
      title: form.title.trim(),
      authors,
      published: form.published,
      summary: form.summary,
      category: form.category.trim() || null,
      doi: doi || null,
      url: form.url.trim() || null,
    },
  }
}

/** BibTeX fields beyond linXiv's own, in `.bib` order (server: app/bib_store.py BIB_FIELDS). */
export const BIB_FIELDS: { key: BibKey; label: string }[] = [
  { key: 'entry_type', label: 'Entry type' },
  { key: 'booktitle', label: 'Book / proceedings title' },
  { key: 'editor', label: 'Editor' },
  { key: 'edition', label: 'Edition' },
  { key: 'series', label: 'Series' },
  { key: 'volume', label: 'Volume' },
  { key: 'number', label: 'Number / issue' },
  { key: 'chapter', label: 'Chapter' },
  { key: 'pages', label: 'Pages' },
  { key: 'month', label: 'Month' },
  { key: 'publisher', label: 'Publisher' },
  { key: 'address', label: 'Publisher address' },
  { key: 'school', label: 'School' },
  { key: 'institution', label: 'Institution' },
  { key: 'organization', label: 'Organization' },
  { key: 'howpublished', label: 'How published' },
  { key: 'note', label: 'Note' },
  { key: 'issn', label: 'ISSN' },
  { key: 'isbn', label: 'ISBN' },
  { key: 'eprint', label: 'E-print' },
  { key: 'archive_prefix', label: 'Archive prefix' },
  { key: 'primary_class', label: 'Primary class' },
]

/** BibTeX fields where the source has a value that differs from the stored one. */
export const bibDiffs = (current: BibFields | undefined | null, found: BibFields | undefined | null) =>
  BIB_FIELDS.filter((f) => {
    const value = norm(found?.[f.key] ?? '')
    return value !== '' && value !== norm(current?.[f.key] ?? '')
  })

/** Recorded with a saved candidate, so "Refresh metadata" can ask the same source again. */
export const candidateSource = (c: MetadataCandidate): MetadataSource => ({ source: c.source, ref: c.ref })

/** The BibTeX part of a save: the picked found values, or (`picked` omitted) all of them.
 * Undefined when the candidate carries none, so the server reads them itself (title-search
 * candidates from Crossref / OpenAlex). */
export function bibInput(c: MetadataCandidate, picked?: ReadonlySet<BibKey>): MetadataInput['bib'] {
  if (!c.bib) return undefined
  return Object.fromEntries(
    BIB_FIELDS.filter((f) => c.bib?.[f.key] && (!picked || picked.has(f.key))).map((f) => [f.key, c.bib?.[f.key]]),
  )
}
