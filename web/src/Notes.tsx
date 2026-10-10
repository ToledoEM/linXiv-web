import { useCallback, useEffect, useState } from 'react'
import { api, saveBlob } from './api'
import { ErrorText } from './components'
import { NoteMarkdown } from './NoteMarkdown'
import { MathText } from './tex'
import { noteFileName, notesMarkdown } from './notesMarkdown'
import type { Note, Paper, Project } from './types'
import { submitOnCtrlEnter } from './submitShortcut'

const when = (ts: string) => ts.replace('T', ' ').slice(0, 16)
const words = (s: string) => (s.trim() ? s.trim().split(/\s+/).length : 0)

// A note may be scoped to a project the paper has since left (or an archived
// one); fall back to a neutral label rather than implying it is global.
function scopeLabel(projectId: number | null, projects: Project[]): string {
  if (projectId == null) return 'Global'
  return projects.find((p) => p.id === projectId)?.name ?? 'Project-scoped'
}

function NoteEditor({
  sourceId,
  projects,
  defaultProjectId,
  initial,
  onSaved,
  onCancel,
}: {
  sourceId: string
  projects: Project[]
  defaultProjectId: number | null
  initial?: Note
  onSaved: () => Promise<void>
  onCancel: () => void
}) {
  const [title, setTitle] = useState(initial?.title ?? '')
  const [content, setContent] = useState(initial?.content ?? '')
  // Scope is set at creation only: `note update` can't move a note.
  const [projectId, setProjectId] = useState<number | null>(initial ? initial.project_id : defaultProjectId)
  const [tab, setTab] = useState<'write' | 'preview'>('write')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const canSave = !saving && !!(title.trim() || content.trim())

  const save = async () => {
    if (!canSave) return
    setSaving(true)
    setError('')
    try {
      if (initial) await api.updateNote(initial.id, { title: title.trim(), content: content.trim() })
      else await api.createNote({ source_id: sourceId, project_id: projectId, title: title.trim(), content: content.trim() })
      await onSaved()
    } catch (err) {
      setError((err as Error).message)
      setSaving(false)
    }
  }

  return (
    <div className="card note-editor" onKeyDown={submitOnCtrlEnter(() => void save())}>
      <label className="field">
        <span>Scope</span>
        {initial || projects.length === 0 ? (
          <span className="pill">{scopeLabel(projectId, projects)}</span>
        ) : (
          <select
            aria-label="Note scope"
            value={projectId ?? ''}
            onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : null)}
            disabled={saving}
          >
            <option value="">Global</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        )}
      </label>
      <input placeholder="Note title" value={title} onChange={(e) => setTitle(e.target.value)} disabled={saving} />
      <div className="segmented note-tabs" role="group" aria-label="Note editor mode">
        {(['write', 'preview'] as const).map((t) => (
          <button key={t} type="button" className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
            {t === 'write' ? 'Write' : 'Preview'}
          </button>
        ))}
      </div>
      {tab === 'write' ? (
        <textarea
          rows={8}
          placeholder="Note content… (Markdown and $TeX$ math)"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          disabled={saving}
        />
      ) : (
        <div className="note-body note-preview">
          {content.trim() ? <NoteMarkdown content={content} /> : <span className="muted">Nothing to preview.</span>}
        </div>
      )}
      <div className="note-foot muted small">
        <span>{words(content) === 1 ? '1 word' : `${words(content)} words`}</span>
        <span>{scopeLabel(projectId, projects)}</span>
      </div>
      <ErrorText error={error} />
      <div className="actions">
        <button onClick={save} disabled={!canSave}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button className="link" onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </div>
  )
}

function NoteCard({
  note,
  projects,
  onEdit,
  onDelete,
}: {
  note: Note
  projects: Project[]
  onEdit: () => void
  onDelete: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [armed, setArmed] = useState(false)
  const edited = Date.parse(note.updated_at) !== Date.parse(note.created_at)
  return (
    <li className="card note-card">
      <div className="note-head">
        <strong>
          <MathText forceInline>{note.title || 'Untitled note'}</MathText>
        </strong>
        <span className="pill">{scopeLabel(note.project_id, projects)}</span>
        <span className="muted small">
          {when(edited ? note.updated_at : note.created_at)}
          {edited && ' · edited'}
        </span>
      </div>
      {note.content && (
        <div
          className={`note-body${open ? '' : ' clamped'}`}
          role="button"
          tabIndex={0}
          title={open ? 'Collapse' : 'Expand'}
          onClick={() => !window.getSelection()?.toString() && setOpen((o) => !o)}
          onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setOpen((o) => !o))}
        >
          <NoteMarkdown content={note.content} forceInline={!open} />
        </div>
      )}
      <div className="actions">
        <button className="link" onClick={onEdit}>
          Edit
        </button>
        {armed ? (
          <>
            <button className="danger armed" onClick={onDelete}>
              Delete forever
            </button>
            <button className="link" onClick={() => setArmed(false)}>
              Cancel
            </button>
          </>
        ) : (
          <button className="link" onClick={() => setArmed(true)}>
            Delete
          </button>
        )}
      </div>
    </li>
  )
}

/** Notes on one paper (desktop PaperDetailPage notes panel). */
export default function Notes({
  sourceId,
  defaultProjectId,
  paper,
}: {
  sourceId: string
  defaultProjectId: number | null
  /** For the Markdown export's frontmatter. */
  paper?: Paper
}) {
  const [notes, setNotes] = useState<Note[] | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [editing, setEditing] = useState<'new' | number | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [n, active, archived] = await Promise.all([
        api.notes({ paper: sourceId }),
        api.projects('active'),
        api.projects('archived'),
      ])
      setNotes(n)
      // Active projects holding this paper are offered as scopes; archived ones only label old notes.
      setProjects([...active, ...archived].filter((p) => p.source_ids.includes(sourceId)))
      setError('')
    } catch (err) {
      setError((err as Error).message)
    }
  }, [sourceId])

  useEffect(() => {
    void load()
  }, [load])

  const saved = async () => {
    setEditing(null)
    await load()
  }

  const remove = async (n: Note) => {
    try {
      await api.deleteNote(n.id)
      await load()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const scopes = projects.filter((p) => p.status === 'active')
  const fromProject = scopes.some((p) => p.id === defaultProjectId) ? defaultProjectId : null

  return (
    <>
      <div className="section-head">
        <h3>Notes{notes?.length ? ` (${notes.length})` : ''}</h3>
        {editing === null && (
          <div className="actions-inline">
            {paper && notes && notes.length > 0 && (
              <button
                title="Download these notes as one Markdown file (Obsidian frontmatter)"
                onClick={() =>
                  saveBlob(
                    new Blob([notesMarkdown(paper, notes, (id) => scopeLabel(id, projects))], {
                      type: 'text/markdown;charset=utf-8',
                    }),
                    `${noteFileName(paper)}.md`,
                  )
                }
              >
                Export .md
              </button>
            )}
            <button onClick={() => setEditing('new')}>New note</button>
          </div>
        )}
      </div>
      <ErrorText error={error} />
      {editing === 'new' && (
        <NoteEditor
          sourceId={sourceId}
          projects={scopes}
          defaultProjectId={fromProject}
          onSaved={saved}
          onCancel={() => setEditing(null)}
        />
      )}
      {notes && notes.length === 0 && editing === null && <p className="muted small">No notes on this paper.</p>}
      {notes && notes.length > 0 && (
        <ul className="note-list">
          {notes.map((n) =>
            editing === n.id ? (
              <li key={n.id}>
                <NoteEditor
                  sourceId={sourceId}
                  projects={projects}
                  defaultProjectId={null}
                  initial={n}
                  onSaved={saved}
                  onCancel={() => setEditing(null)}
                />
              </li>
            ) : (
              <NoteCard
                key={n.id}
                note={n}
                projects={projects}
                onEdit={() => setEditing(n.id)}
                onDelete={() => remove(n)}
              />
            ),
          )}
        </ul>
      )}
    </>
  )
}
