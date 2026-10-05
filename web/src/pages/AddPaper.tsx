import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, idPath } from '../api'
import { ErrorText } from '../components'
import { MathText } from '../tex'

type Added = { input: string; kind?: string; source_id?: string; title?: string; error?: string }

const KIND_LABEL: Record<string, string> = { arxiv: 'arXiv', doi: 'DOI', pdf: 'PDF link' }

export default function AddPaper() {
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [added, setAdded] = useState<Added[]>([])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const text = input.trim()
    if (!text) return
    setBusy(true)
    try {
      const r = await api.add(text)
      setAdded((prev) => [{ input: text, kind: r.kind, source_id: r.paper.source_id, title: r.paper.title }, ...prev])
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
        Paste an arXiv link or id, a DOI or doi.org link, or a direct link to a PDF.
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
              <Link to={`/paper/${idPath(a.source_id)}`}>
                <MathText forceInline>{a.title || a.source_id}</MathText>
              </Link>
            )}
            <ErrorText error={a.error} />
          </li>
        ))}
      </ul>
    </section>
  )
}
