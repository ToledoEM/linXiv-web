import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, idPath } from '../api'
import { ErrorText } from '../components'
import { MathText } from '../tex'
import type { Author, AuthorDetail as Detail, AuthorUpdate, MergeCandidates } from '../types'

type Field = keyof AuthorUpdate
const FIELDS: { key: Field; label: string; placeholder: string }[] = [
  { key: 'full_name', label: 'Full name', placeholder: 'Full name' },
  { key: 'first_name', label: 'First name', placeholder: 'First name' },
  { key: 'last_name', label: 'Last name', placeholder: 'Last name' },
  { key: 'orcid', label: 'ORCID', placeholder: '0000-0000-0000-0000' },
]
// Unfiltered merge picker shows this many; typing a filter shows every match.
const PICKER_CAP = 50

const nameOf = (a: { full_name: string | null }) => a.full_name ?? '(unnamed)'

// Full, first or last name, and ORCID (same as the Authors list filter).
function matches(a: Author, q: string): boolean {
  if (!q) return true
  return [a.full_name, a.first_name, a.last_name, a.orcid].some((f) => f?.toLowerCase().includes(q))
}

function OrcidLink({ orcid }: { orcid: string }) {
  return (
    <a className="mono" href={`https://orcid.org/${encodeURIComponent(orcid)}`} target="_blank" rel="noreferrer">
      {orcid}
    </a>
  )
}

function EditForm({ author, onSaved, onCancel }: { author: Detail; onSaved: () => void; onCancel: () => void }) {
  const [form, setForm] = useState<Record<Field, string>>({
    full_name: author.full_name ?? '',
    first_name: author.first_name ?? '',
    last_name: author.last_name ?? '',
    orcid: author.orcid ?? '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    // Send only non-blank fields that changed: linxiv ignores blanks and cannot clear a value.
    const body: AuthorUpdate = {}
    for (const { key } of FIELDS) {
      const v = form[key].trim()
      if (v && v !== (author[key] ?? '')) body[key] = v
    }
    if (Object.keys(body).length === 0) return onCancel()
    setBusy(true)
    setError('')
    try {
      await api.updateAuthor(author.author_id, body)
      onSaved()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <form className="card author-form" onSubmit={submit}>
      {FIELDS.map(({ key, label, placeholder }) => (
        <label key={key} className="field">
          <span>{label}</span>
          <input
            value={form[key]}
            placeholder={placeholder}
            onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
            spellCheck={key !== 'orcid'}
          />
        </label>
      ))}
      <p className="muted small">Blank fields are ignored; clearing a value is not supported.</p>
      <ErrorText error={error} />
      <div className="actions">
        <button type="submit" disabled={busy}>
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="link" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  )
}

export default function AuthorDetail() {
  const { id } = useParams()
  const authorId = id && /^\d+$/.test(id) ? Number(id) : NaN
  const navigate = useNavigate()
  const [author, setAuthor] = useState<Detail | null>(null)
  const [suggest, setSuggest] = useState<MergeCandidates | null>(null)
  const [loadError, setLoadError] = useState('')
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  // Two-click confirm: one shared key, so arming one action disarms the others.
  const [armed, setArmed] = useState<string | null>(null)
  const [allAuthors, setAllAuthors] = useState<Author[]>([])
  const [filter, setFilter] = useState('')
  const [picked, setPicked] = useState<number[]>([])

  const load = useCallback(async () => {
    if (Number.isNaN(authorId)) {
      setLoadError('Author not found')
      return
    }
    try {
      const [a, s, all] = await Promise.all([api.author(authorId), api.mergeCandidates(authorId), api.authors(false)])
      setAuthor(a)
      setSuggest(s)
      setAllAuthors(all)
      setLoadError('')
    } catch (err) {
      setLoadError((err as Error).message)
    }
  }, [authorId])

  useEffect(() => {
    load()
  }, [load])

  const pickerMatches = useMemo(() => {
    const needle = filter.trim().toLowerCase()
    return allAuthors.filter((a) => a.author_id !== authorId && matches(a, needle))
  }, [allAuthors, authorId, filter])
  const pickerOptions = filter.trim() ? pickerMatches : pickerMatches.slice(0, PICKER_CAP)

  const merge = async (ids: number[]) => {
    setArmed(null)
    setBusy(true)
    setError('')
    setNotice('')
    try {
      const r = await api.mergeAuthors(authorId, ids)
      const n = r.merged_ids.length
      setNotice(n ? `Merged ${n} author${n === 1 ? '' : 's'} into this one.` : 'Nothing merged: those authors no longer exist.')
      setPicked([])
      setFilter('')
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const remove = async () => {
    setArmed(null)
    setBusy(true)
    setError('')
    try {
      await api.deleteAuthor(authorId)
      navigate('/authors')
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  // First click arms `key`, second click on the same key runs `action`.
  const armOr = (key: string, action: () => void) => () => (armed === key ? action() : setArmed(key))

  const back = (
    <p className="small">
      <Link to="/authors">← Authors</Link>
    </p>
  )
  if (loadError) {
    return (
      <section>
        {back}
        <ErrorText error={loadError} />
      </section>
    )
  }
  if (!author || !suggest) return <p className="muted">Loading…</p>

  const orcidDupes = suggest.candidates
  const linked = author.papers.length

  return (
    <section className="author-detail">
      {back}
      {editing ? (
        <EditForm
          author={author}
          onCancel={() => setEditing(false)}
          onSaved={() => {
            setEditing(false)
            load()
          }}
        />
      ) : (
        <>
          <div className="page-head">
            <h2>{nameOf(author)}</h2>
            <button
              className="page-head-action"
              onClick={() => {
                setNotice('')
                setEditing(true)
              }}
            >
              Edit
            </button>
          </div>
          <dl className="kv">
            <dt>First name</dt>
            <dd>{author.first_name ?? <span className="muted">—</span>}</dd>
            <dt>Last name</dt>
            <dd>{author.last_name ?? <span className="muted">—</span>}</dd>
            <dt>ORCID</dt>
            <dd>{author.orcid ? <OrcidLink orcid={author.orcid} /> : <span className="muted">—</span>}</dd>
          </dl>
        </>
      )}

      <ErrorText error={error} />
      {notice && <p className="success">{notice}</p>}

      <h3>Papers ({linked})</h3>
      <p className="muted small">Editing this author's name does not change the author list stored with each paper.</p>
      {linked === 0 ? (
        <p className="muted">No papers linked to this author.</p>
      ) : (
        <ul className="results">
          {author.papers.map((p) => (
            <li key={p.paper_id} className="card author-paper">
              <Link to={`/paper/${idPath(p.source_id)}`}>
                <MathText forceInline>{p.title ?? p.source_id}</MathText>
              </Link>
              <span className="muted small mono">
                {p.source_id} · v{p.version}
              </span>
            </li>
          ))}
        </ul>
      )}

      <h3>Merge duplicates</h3>
      <p className="muted small">
        Pick other records for the same person. Their papers move to this author and the duplicate records are
        deleted. This cannot be undone.
      </p>
      {orcidDupes.length > 0 && (
        <div className="card merge-hint">
          <p>
            Same ORCID as {orcidDupes.map(nameOf).join(', ')}: likely the same person.
          </p>
          <div className="actions">
            <button
              className={armed === 'merge:orcid' ? 'danger armed' : ''}
              disabled={busy}
              onClick={armOr('merge:orcid', () => merge(orcidDupes.map((a) => a.author_id)))}
            >
              {armed === 'merge:orcid'
                ? 'Confirm merge: cannot be undone'
                : `Merge duplicate${orcidDupes.length > 1 ? 's' : ''}`}
            </button>
            {armed === 'merge:orcid' && (
              <button className="link" onClick={() => setArmed(null)}>
                Cancel
              </button>
            )}
          </div>
        </div>
      )}
      {suggest.name_candidates.length > 0 && (
        <div className="card merge-hint">
          <p className="muted">
            Same name, separate record{suggest.name_candidates.length > 1 ? 's' : ''}. Might be the same person, but a
            shared name alone is weak evidence.
          </p>
          <ul className="plain">
            {suggest.name_candidates.map((c) => (
              <li key={c.author_id}>
                <Link to={`/authors/${c.author_id}`}>{nameOf(c)}</Link>
                {c.orcid && <span className="muted small"> · ORCID {c.orcid}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="merge-picker">
        <input
          placeholder="Filter authors…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <select
          multiple
          aria-label="Authors to merge into this author"
          size={8}
          value={picked.map(String)}
          onChange={(e) => setPicked(Array.from(e.target.selectedOptions, (o) => Number(o.value)))}
        >
          {pickerOptions.map((a) => (
            <option key={a.author_id} value={a.author_id}>
              {nameOf(a)} ({a.paper_count}){a.orcid ? ` · ${a.orcid}` : ''}
            </option>
          ))}
        </select>
        {!filter.trim() && pickerMatches.length > pickerOptions.length && (
          <span className="muted small">
            Showing {pickerOptions.length} of {pickerMatches.length} authors. Type to filter.
          </span>
        )}
        <div className="actions">
          <button
            className={armed === 'merge:picker' ? 'danger armed' : ''}
            disabled={busy || picked.length === 0}
            onClick={armOr('merge:picker', () => merge(picked))}
          >
            {busy
              ? 'Merging…'
              : armed === 'merge:picker'
                ? `Confirm merge of ${picked.length}: cannot be undone`
                : `Merge${picked.length ? ` ${picked.length}` : ''} into this author`}
          </button>
          {armed === 'merge:picker' && (
            <button className="link" onClick={() => setArmed(null)}>
              Cancel
            </button>
          )}
        </div>
      </div>

      <h3 className="danger-head">Danger zone</h3>
      <div className="actions">
        <button
          className={armed === 'delete' ? 'danger armed' : 'danger'}
          disabled={busy || linked > 0}
          onClick={armOr('delete', remove)}
        >
          {armed === 'delete' ? 'Confirm delete' : 'Delete author'}
        </button>
        {armed === 'delete' && (
          <button className="link" onClick={() => setArmed(null)}>
            Cancel
          </button>
        )}
      </div>
      {linked > 0 && (
        <p className="muted small">
          Cannot delete: linked to {linked} paper{linked === 1 ? '' : 's'}. Merge it into another author instead.
        </p>
      )}
    </section>
  )
}
