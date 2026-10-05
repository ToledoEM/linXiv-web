import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, idPath } from '../api'
import type { Paper, Project } from '../types'
import { ErrorText } from '../components'
import { failedMessage, toggled } from '../projects'
import { MathText } from '../tex'

type PdfFilter = 'all' | 'has' | 'none'

const PDF_FILTERS: { value: PdfFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'has', label: 'Has PDF' },
  { value: 'none', label: 'No PDF' },
]

// Same choices as linXiv desktop's Library.
const SORTS = [
  { value: 'published_desc', label: 'Newest first' },
  { value: 'published_asc', label: 'Oldest first' },
  { value: 'added_desc', label: 'Recently added' },
  { value: 'added_asc', label: 'First added' },
  { value: 'title_asc', label: 'Title A–Z' },
  { value: 'title_desc', label: 'Title Z–A' },
] as const

/** Add the selected papers to an existing or new project (desktop Library SelectionBar). */
function AddToProjectBar({
  selected,
  onSelect,
}: {
  selected: Set<string>
  onSelect: (ids: Set<string>) => void
}) {
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [target, setTarget] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState('')

  useEffect(() => {
    api
      .projects('active')
      .then(setProjects)
      .catch((err) => setError((err as Error).message))
  }, [])

  const addTo = async (projectId: number, label: string, created: boolean) => {
    const ids = [...selected]
    const r = await api.addProjectPapers(projectId, ids)
    if (r.failed.length) {
      // Keep only the failures selected so a retry can't re-add the rest.
      onSelect(new Set(r.failed))
      setError(created ? `Project created, but ${failedMessage(r.failed.length, ids.length)}` : failedMessage(r.failed.length, ids.length))
    } else {
      onSelect(new Set())
      setDone(`Added ${ids.length} paper${ids.length === 1 ? '' : 's'} to ${label}.`)
    }
  }

  const go = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError('')
    setDone('')
    try {
      await fn()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const addExisting = () =>
    go(async () => {
      const p = projects?.find((x) => String(x.id) === target)
      if (p) await addTo(p.id, p.name, false)
    })

  const addNew = () =>
    go(async () => {
      const label = name.trim()
      const { id } = await api.createProject({ name: label, description: '', color_hex: null, project_tags: [] })
      // The project exists either way; clear the name so a retry can't duplicate it.
      setName('')
      setProjects(await api.projects('active'))
      await addTo(id, label, true)
    })

  if (!selected.size) return done ? <p className="success small">{done}</p> : null

  return (
    <div className="selection-bar">
      <span>{selected.size} selected</span>
      <select aria-label="Project" value={target} onChange={(e) => setTarget(e.target.value)} disabled={busy}>
        <option value="">Choose project…</option>
        {projects?.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
      <button onClick={addExisting} disabled={busy || !target}>
        Add to project
      </button>
      <span className="muted small">or</span>
      <input
        placeholder="New project name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && name.trim() && !busy && addNew()}
        disabled={busy}
      />
      <button onClick={addNew} disabled={busy || !name.trim()}>
        Create and add
      </button>
      <span className="grow" />
      <button className="link" onClick={() => onSelect(new Set())} disabled={busy}>
        Clear
      </button>
      {error && <p className="error selection-bar-msg">{error}</p>}
    </div>
  )
}

export default function Library() {
  const [q, setQ] = useState('')
  const [params] = useSearchParams()
  const [tag, setTag] = useState(() => params.get('tag') ?? '')
  const [fulltext, setFulltext] = useState(false)
  const [sort, setSort] = useState<string>(SORTS[0].value)
  const [pdf, setPdf] = useState<PdfFilter>('all')
  const [tags, setTags] = useState<string[]>([])
  const [papers, setPapers] = useState<Paper[] | null>(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  useEffect(() => {
    api.allTags().then(setTags).catch(() => setTags([]))
  }, [])

  useEffect(() => {
    let cancelled = false
    const t = setTimeout(() => {
      const [by, dir] = sort.split('_') as [string, 'asc' | 'desc']
      api
        .papers({
          q: q.trim() || undefined,
          tag: tag || undefined,
          fulltext: fulltext || undefined,
          sort: by,
          dir,
          pdf: pdf === 'all' ? undefined : pdf,
          limit: 500,
        })
        .then((p) => {
          if (!cancelled) {
            setPapers(p)
            setError('')
          }
        })
        .catch((err) => !cancelled && setError((err as Error).message))
    }, 250)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [q, tag, fulltext, sort, pdf])

  const allShownSelected = !!papers?.length && papers.every((p) => selected.has(p.source_id))

  return (
    <section>
      <h2>Library</h2>
      <p className="muted small library-count">
        {papers ? `${papers.length} paper${papers.length === 1 ? '' : 's'}` : '\u00a0'}
      </p>
      <div className="toolbar">
        <div className="chips" role="group" aria-label="PDF filter">
          {PDF_FILTERS.map((f) => (
            <button
              key={f.value}
              className={pdf === f.value ? 'chip active' : 'chip'}
              aria-pressed={pdf === f.value}
              disabled={fulltext}
              onClick={() => setPdf(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <span className="grow" />
        <select aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value)} disabled={fulltext}>
          {SORTS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="toolbar">
        <input
          className="grow"
          placeholder={fulltext ? 'Full-text search (indexed TeX sources)' : 'Filter by title, author, id, tag…'}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <label className="check">
          <input type="checkbox" checked={fulltext} onChange={(e) => setFulltext(e.target.checked)} />
          Full text
        </label>
        <select value={tag} onChange={(e) => setTag(e.target.value)} disabled={fulltext}>
          <option value="">All tags</option>
          {tags.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
      <ErrorText error={error} />
      <AddToProjectBar selected={selected} onSelect={setSelected} />
      {papers && papers.length === 0 && <p className="muted">No papers.</p>}
      {papers && papers.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="check-col">
                  <input
                    type="checkbox"
                    aria-label="Select all shown"
                    checked={allShownSelected}
                    onChange={() => {
                      const next = new Set(selected)
                      for (const p of papers) {
                        if (allShownSelected) next.delete(p.source_id)
                        else next.add(p.source_id)
                      }
                      setSelected(next)
                    }}
                  />
                </th>
                <th>Title</th>
                <th>Authors</th>
                <th>Published</th>
                <th>Category</th>
                <th>Tags</th>
                <th>PDF</th>
              </tr>
            </thead>
            <tbody>
              {papers.map((p) => (
                <tr key={p.source_id}>
                  <td className="check-col">
                    <input
                      type="checkbox"
                      aria-label={`Select ${p.source_id}`}
                      checked={selected.has(p.source_id)}
                      onChange={() => setSelected((s) => toggled(s, p.source_id))}
                    />
                  </td>
                  <td>
                    <Link to={`/paper/${idPath(p.source_id)}`}>
                      <MathText forceInline>{p.title}</MathText>
                    </Link>
                  </td>
                  <td className="small">
                    {p.authors?.slice(0, 3).join(', ')}
                    {p.authors?.length > 3 && ' et al.'}
                  </td>
                  <td className="nowrap">{p.published}</td>
                  <td>{p.category}</td>
                  <td>
                    {p.tags?.map((t) => (
                      <span key={t} className="pill">
                        {t}
                      </span>
                    ))}
                  </td>
                  <td>{p.has_pdf ? '✓' : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
