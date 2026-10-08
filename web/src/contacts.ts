// Contact addresses linXiv sends to metadata services (Settings and first-run setup).
export const CONTACTS: { key: 'ARXIV_MAILTO' | 'CROSSREF_MAILTO' | 'OPENALEX_MAILTO'; label: string; hint: string }[] =
  [
    { key: 'ARXIV_MAILTO', label: 'arXiv', hint: 'Sent in the User-Agent of arXiv requests.' },
    { key: 'CROSSREF_MAILTO', label: 'Crossref', hint: 'Crossref polite pool.' },
    { key: 'OPENALEX_MAILTO', label: 'OpenAlex', hint: 'OpenAlex polite pool.' },
  ]
