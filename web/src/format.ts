import type { Paper } from './types'

/** A paper's title, else its PDF file name, else its id: never an empty link. */
export function paperLabel(p: Pick<Paper, 'title' | 'pdf_file' | 'source_id'>): string {
  return p.title?.trim() || p.pdf_file || p.source_id
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

const DOI_URL = /^(?:https?:\/\/)?(?:dx\.|www\.)?doi\.org\//i
const DOI_PREFIX = /^doi:\s*/i
const DOI_LEAD = /^[\s"';,.:<>([{]+/
const DOI_START = /10\.\d{4,9}\/\S+/
const DOI_TRAIL = /[\s"';,.:>]$/
const DOI_CLOSE: Record<string, string> = { ')': '(', ']': '[', '}': '{' }
const count = (s: string, c: string) => s.split(c).length - 1
// Crossref's patterns (crossref.org/blog/dois-and-matching-regular-expressions): the
// modern form, then older Wiley, SICI (literal parentheses), ACS and 10.1207 forms.
const DOI_VALID = [
  /^10\.\d{4,9}\/[-._;()/:A-Z0-9]+$/i,
  /^10\.1002\/\S+$/i,
  /^10\.\d{4}\/\d+-\d+X?\(\d+\)\d+<\w+:\w*>\d+\.\d+\.\w+;\d$/i,
  /^10\.1021\/\w\w\d+$/i,
  /^10\.1207\/\w+&\d+_\d+$/i,
]

function decode(s: string): string {
  try {
    return decodeURIComponent(s)
  } catch {
    return s
  }
}

/** The DOI in `value`, without the text, quotes and punctuation around it and
 * without a `doi:` / doi.org prefix (percent-decoded); '' when none. Starts at the
 * first `10.<registrant>/`, stops at whitespace; only the end is trimmed, so `;` and
 * brackets inside a DOI stay. Same rule as server `app/doi.py`. */
export function cleanDoi(value?: string | null): string {
  let doi = (value ?? '').replace(DOI_LEAD, '')
  const url = DOI_URL.exec(doi)
  if (url) doi = decode(doi.slice(url[0].length))
  doi = doi.replace(DOI_PREFIX, '').replace(DOI_LEAD, '')
  const start = DOI_START.exec(doi)
  if (start) doi = start[0]
  for (;;) {
    const last = doi.slice(-1)
    if (!last) break
    if (DOI_TRAIL.test(last) || (last in DOI_CLOSE && count(doi, last) > count(doi, DOI_CLOSE[last]))) {
      doi = doi.slice(0, -1)
    } else break
  }
  return doi
}

/** `doi` (already cleaned) has a shape Crossref's patterns accept. */
export const isValidDoi = (doi: string) => DOI_VALID.some((p) => p.test(doi))

/** The cleaned DOI when valid, else '' (shown, linked and exported as no DOI). */
export function validDoi(value?: string | null): string {
  const doi = cleanDoi(value)
  return doi && isValidDoi(doi) ? doi : ''
}

// arXiv subject codes (cs.CL, hep-th, q-bio.GN): a subject, not a venue.
const ARXIV_SUBJECT = /^[a-z-]+(\.[A-Za-z-]+)?$/

/** Where a paper was published: the stored journal (category), else the journal
 * reference. arXiv papers skip a category that is an arXiv subject code and fall back to
 * "arXiv preprint". */
export function paperJournal(p: Pick<Paper, 'source_id' | 'category' | 'journal_ref'>): string {
  const category = p.category?.trim() ?? ''
  const ref = p.journal_ref?.trim() ?? ''
  if (p.source_id.startsWith('arxiv:')) {
    return (!ARXIV_SUBJECT.test(category) && category) || ref || 'arXiv preprint'
  }
  return category || ref
}
