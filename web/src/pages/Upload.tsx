import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, idPath } from '../api'
import { ErrorText } from '../components'

type Result = { name: string; source_id?: string; title?: string; error?: string }

export default function Upload() {
  const [files, setFiles] = useState<File[]>([])
  const [results, setResults] = useState<Result[]>([])
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    const out: Result[] = []
    // One at a time: the server serializes linxiv calls anyway.
    for (const f of files) {
      try {
        const r = await api.importPdf(f)
        out.push({ name: f.name, ...r })
      } catch (err) {
        out.push({ name: f.name, error: (err as Error).message })
      }
      setResults([...out])
    }
    setBusy(false)
    setFiles([])
  }

  return (
    <section>
      <h2>Upload PDFs</h2>
      <p className="muted">linXiv extracts metadata from each PDF and adds it to the library.</p>
      <form className="toolbar" onSubmit={submit}>
        <input
          type="file"
          accept="application/pdf,.pdf"
          multiple
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        <button disabled={busy || files.length === 0}>{busy ? 'Importing…' : 'Import'}</button>
      </form>
      <ul className="results">
        {results.map((r, i) => (
          <li key={i} className="card">
            <strong>{r.name}</strong>
            {r.source_id && (
              <div>
                <Link to={`/paper/${idPath(r.source_id)}`}>{r.title || r.source_id}</Link>
              </div>
            )}
            <ErrorText error={r.error} />
          </li>
        ))}
      </ul>
    </section>
  )
}
