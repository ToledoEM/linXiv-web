import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ErrorText } from '../components'
import { DeleteButton, Swatch } from '../projectParts'
import { isReadingList, READING_LIST_TAG } from '../projects'
import { MathText } from '../tex'
import type { Project } from '../types'
import { formSubmitOnCtrlEnter } from '../submitShortcut'

/** A reading list IS a project carrying the reserved `reading-list` tag (desktop ReadingListsPage). */
function NewReadingList({ onCreated, onCancel }: { onCreated: () => Promise<void>; onCancel: () => void }) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      await api.createProject({ name: name.trim(), description: '', color_hex: null, project_tags: [READING_LIST_TAG] })
      await onCreated()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <form className="card project-form" onSubmit={submit} onKeyDown={formSubmitOnCtrlEnter}>
      <label className="field">
        <span>Name</span>
        <input
          id="rl-name"
          value={name}
          placeholder="Reading list name"
          onChange={(e) => setName(e.target.value)}
          required
          autoFocus
        />
      </label>
      <ErrorText error={error} />
      <div className="actions">
        <button type="submit" disabled={!name.trim() || busy}>
          {busy ? 'Creating…' : 'Create'}
        </button>
        <button type="button" className="link" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  )
}

export default function ReadingLists() {
  const [showArchived, setShowArchived] = useState(false)
  const [lists, setLists] = useState<Project[] | null>(null)
  const [archivedCount, setArchivedCount] = useState(0)
  const [creating, setCreating] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [list, archived] = await Promise.all([
        api.projects(showArchived ? 'archived' : 'active'),
        showArchived ? null : api.projects('archived'),
      ])
      const own = list.filter(isReadingList)
      setLists(own)
      setArchivedCount(archived ? archived.filter(isReadingList).length : own.length)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [showArchived])

  useEffect(() => {
    void load()
  }, [load])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError('')
    try {
      await fn()
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const switchView = (archived: boolean) => {
    setShowArchived(archived)
    setLists(null)
    setCreating(false)
  }

  return (
    <section>
      <div className="page-head">
        <h2>{showArchived ? 'Archived reading lists' : 'Reading lists'}</h2>
        {showArchived ? (
          <button className="link" onClick={() => switchView(false)}>
            ← back
          </button>
        ) : (
          archivedCount > 0 && (
            <button className="link" onClick={() => switchView(true)}>
              {archivedCount} archived
            </button>
          )
        )}
        {!showArchived && !creating && (
          <button className="page-head-action" onClick={() => setCreating(true)}>
            New reading list
          </button>
        )}
      </div>
      <p className="muted small">
        A reading list is a project tagged <span className="mono">{READING_LIST_TAG}</span>. Open one to add papers.
        Per-paper reading status (unread / reading / read) needs a linXiv CLI command that doesn&apos;t exist yet.
      </p>
      <ErrorText error={error} />

      {creating && (
        <NewReadingList
          onCreated={async () => {
            setCreating(false)
            await load()
          }}
          onCancel={() => setCreating(false)}
        />
      )}

      {!lists ? (
        !error && <p className="muted">Loading…</p>
      ) : lists.length === 0 ? (
        <p className="muted">
          {showArchived ? 'No archived reading lists.' : 'No reading lists. Create one, then add papers to it.'}
        </p>
      ) : (
        <ul className="project-grid">
          {lists.map((p) => {
            const tags = p.project_tags.filter((t) => t.toLowerCase() !== READING_LIST_TAG)
            const n = p.paper_count ?? p.source_ids.length
            return (
              <li key={p.id} className="card project-card">
                <div className="project-name">
                  <Swatch color={p.color_hex} />
                  <Link to={`/projects/${p.id}`}>
                    <strong>{p.name}</strong>
                  </Link>
                </div>
                {p.description && (
                  <div className="project-desc muted small">
                    <MathText forceInline>{p.description}</MathText>
                  </div>
                )}
                <div className="tags">
                  <span className="pill">
                    {n} paper{n === 1 ? '' : 's'}
                  </span>
                  {tags.slice(0, 3).map((t) => (
                    <span key={t} className="pill pill-tag">
                      {t}
                    </span>
                  ))}
                </div>
                <div className="actions">
                  {showArchived ? (
                    <button disabled={busy} onClick={() => act(() => api.unarchiveProject(p.id))}>
                      Restore
                    </button>
                  ) : (
                    <button disabled={busy} onClick={() => act(() => api.archiveProject(p.id))}>
                      Archive
                    </button>
                  )}
                  <DeleteButton busy={busy} onConfirm={() => act(() => api.deleteProject(p.id))} />
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
