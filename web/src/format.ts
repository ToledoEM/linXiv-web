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

const DOI_PREFIX = /^(?:doi:\s*|https?:\/\/(?:dx\.|www\.)?doi\.org\/)/i
const DOI_LEAD = /^[\s"';,.:<>([{]+/
const DOI_TRAIL = /[\s"';,.:>]$/
const DOI_CLOSE: Record<string, string> = { ')': '(', ']': '[', '}': '{' }
const count = (s: string, c: string) => s.split(c).length - 1

/** A DOI without the whitespace, quotes and punctuation around it (PDF text often
 * leaves `;` or spaces) and without a `doi:` / doi.org prefix; '' when none. Only the
 * ends change: `;` and brackets inside a DOI stay. Same rule as server `app/doi.py`. */
export function cleanDoi(value?: string | null): string {
  let doi = (value ?? '').replace(DOI_LEAD, '').replace(DOI_PREFIX, '').replace(DOI_LEAD, '')
  for (;;) {
    const last = doi.slice(-1)
    if (!last) break
    if (DOI_TRAIL.test(last) || (last in DOI_CLOSE && count(doi, last) > count(doi, DOI_CLOSE[last]))) {
      doi = doi.slice(0, -1)
    } else break
  }
  return doi
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
