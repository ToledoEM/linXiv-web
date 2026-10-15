import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, paperPath } from '../api'
import { ErrorText } from '../components'
import { MathText } from '../tex'

type ImportKind = 'bibtex' | 'zotero'
type Imported = { name: string; kind: ImportKind; saved?: number; ids?: string[]; error?: string }

const kindFor = (name: string): ImportKind => (name.toLowerCase().endsWith('.json') ? 'zotero' : 'bibtex')

type Added = {
  input: string
  kind?: string
  source_id?: string
  title?: string
  pdfSaved?: boolean
  error?: string
}

const KIND_LABEL: Record<string, string> = { arxiv: 'arXiv', doi: 'DOI', pdf: 'PDF link' }

export default function AddPaper() {
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [added, setAdded] = useState<Added[]>([])
  const [files, setFiles] = useState<File[]>([])
  const [importing, setImporting] = useState(false)
  const [imported, setImported] = useState<Imported[]>([])
  const [fileKey, setFileKey] = useState(0)

  const importFiles = async (e: FormEvent) => {
    e.preventDefault()
    setImporting(true)
    // One at a time: the server serializes linxiv calls anyway.
    for (const f of files) {
      const kind = kindFor(f.name)
      try {
        const r = await api.importFile(kind, f)
        setImported((prev) => [{ name: f.name, kind, saved: r.saved_count, ids: r.source_ids }, ...prev])
      } catch (err) {
        setImported((prev) => [{ name: f.name, kind, error: (err as Error).message }, ...prev])
      }
    }
    setImporting(false)
    setFiles([])
    setFileKey((k) => k + 1)
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    setBusy(true)
    try {
      const r = await api.add(text)
      setAdded((prev) => [
        { input: text, kind: r.kind, source_id: r.paper.source_id, title: r.paper.title, pdfSaved: r.pdf_saved },
        ...prev,
      ])
      setInput('')
    } catch (err) {
      setAdded((prev) => [{ input: text, error: (err as Error).message }, ...prev])
    } finally {
      setBusy(false)
    }
  }

  return (
    <section>
      <h2>Add paper</h2>
      <p className="muted">
        Paste an arXiv link or id, a DOI or doi.org link, a publisher article link (Nature, Springer, Wiley, ACS, APS,
        IOP, Science, PNAS and others), or a direct link to a PDF.
      </p>
      <form className="toolbar" onSubmit={submit}>
        <input
          className="grow"
          placeholder="https://arxiv.org/abs/1706.03762 · 10.1038/nature14539 · https://…/paper.pdf"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          autoFocus
        />
        <button disabled={busy || !input.trim()}>{busy ? 'Adding…' : 'Add'}</button>
      </form>
      <ul className="results">
        {added.map((a, i) => (
          <li key={i} className="card">
            <div className="result-head">
              <span className="mono small">{a.input}</span>
              {a.kind && <span className="pill">{KIND_LABEL[a.kind] ?? a.kind}</span>}
            </div>
            {a.source_id && (
              <Link to={paperPath(a.source_id)}>
                <MathText forceInline>{a.title || a.source_id}</MathText>
              </Link>
            )}
            {a.pdfSaved !== undefined && (
              <p className="muted small">
                {a.pdfSaved
                  ? 'PDF downloaded from the publisher.'
                  : 'No PDF: the publisher link didn’t return one (paywall or login). Saved as metadata only.'}
              </p>
            )}
            <ErrorText error={a.error} />
          </li>
        ))}
      </ul>

      <h3>Import a file</h3>
      <p className="muted">
        A BibTeX <span className="mono">.bib</span> file or a Zotero CSL JSON export (
        <span className="mono">.json</span>). Entries already in the library are updated, not duplicated; papers in the trash are restored.
      </p>
      <form className="toolbar" onSubmit={importFiles}>
        <input
          key={fileKey}
          type="file"
          accept=".bib,.bibtex,.json,application/json,application/x-bibtex,text/plain"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        <button disabled={importing || files.length === 0}>{importing ? 'Importing…' : 'Import'}</button>
      </form>
      <ul className="results">
        {imported.map((r, i) => (
          <li key={i} className="card">
            <div className="result-head">
              <span className="mono small">{r.name}</span>
              <span className="pill">{r.kind === 'bibtex' ? 'BibTeX' : 'Zotero CSL JSON'}</span>
            </div>
            {r.saved !== undefined &&
              (r.saved === 0 ? (
                <p className="warn">
                  No papers imported: linXiv found no entries it could read in this file.
                </p>
              ) : (
                <>
                  <p>
                    Saved {r.saved} paper{r.saved === 1 ? '' : 's'} (new or updated).
                  </p>
                  <div className="tags">
                    {r.ids?.map((id) => (
                      <Link key={id} className="pill mono" to={paperPath(id)}>
                        {id}
                      </Link>
                    ))}
                  </div>
                </>
              ))}
            <ErrorText error={r.error} />
          </li>
        ))}
      </ul>
    </section>
  )
}
