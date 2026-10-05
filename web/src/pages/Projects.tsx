import { useCallback, useEffect, useState, type FormEvent, type KeyboardEvent } from 'react'
import { api } from '../api'
import { ErrorText } from '../components'
import { MathText } from '../tex'
import type { Project, ProjectInput } from '../types'

// linXiv desktop src/components/projects/constants.ts
const PRESET_COLORS = ['#5b8dee', '#4caf88', '#e8912d', '#748ffc', '#e05c6c', '#51cf66']
// Reserved tag that turns a project into a reading list (desktop lib/readingStatus.ts).
const READING_LIST_TAG = 'reading-list'

const EMPTY: ProjectInput = { name: '', description: '', color_hex: null, project_tags: [] }

const hasTag = (tags: string[], t: string) => tags.some((x) => x.toLowerCase() === t.toLowerCase())

/** Chips plus a text box: Enter or blur adds, Backspace on empty removes the last. */
function TagInput({ value, onChange, id }: { value: string[]; onChange: (tags: string[]) => void; id: string }) {
  const [draft, setDraft] = useState('')
  const commit = () => {
    const tag = draft.trim()
    if (tag && !hasTag(value, tag)) onChange([...value, tag])
    setDraft('')
  }
  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      commit()
    } else if (e.key === 'Backspace' && !draft && value.length) {
      onChange(value.slice(0, -1))
    }
  }
  return (
    <div className="tag-input">
      {value.map((t) => (
        <span key={t} className="pill">
          {t}
          <button
            type="button"
            className="pill-x"
            aria-label={`Remove ${t}`}
            onClick={() => onChange(value.filter((x) => x !== t))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        id={id}
        value={draft}
        placeholder={value.length ? '' : 'Add tag…'}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={commit}
        autoCapitalize="none"
        spellCheck={false}
      />
    </div>
  )
}

function Swatch({ color }: { color: string | null }) {
  return <span className="swatch" style={{ background: color ?? 'var(--accent)' }} />
}

function ProjectForm({
  initial,
  submitLabel,
  isEdit,
  onSubmit,
  onCancel,
}: {
  initial: ProjectInput
  submitLabel: string
  isEdit: boolean
  onSubmit: (value: ProjectInput) => Promise<void>
  onCancel: () => void
}) {
  const [value, setValue] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const set = (patch: Partial<ProjectInput>) => setValue((v) => ({ ...v, ...patch }))
  const idp = isEdit ? 'edit-proj' : 'new-proj'

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!value.name.trim() || busy) return
    if (isEdit && hasTag(value.project_tags, READING_LIST_TAG) && !hasTag(initial.project_tags, READING_LIST_TAG)) {
      setError('Cannot add the reading-list tag to a project that is not a reading list.')
      return
    }
    setBusy(true)
    setError('')
    try {
      await onSubmit({ ...value, name: value.name.trim(), description: value.description.trim() })
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  // linxiv can set a project color but not remove it, so an edit can only switch colors.
  const pickColor = (c: string) => set({ color_hex: value.color_hex === c && !isEdit ? null : c })

  return (
    <form className="card project-form" onSubmit={submit}>
      <label className="field">
        <span>Name</span>
        <input id={`${idp}-name`} value={value.name} onChange={(e) => set({ name: e.target.value })} required autoFocus />
      </label>
      <label className="field">
        <span>Description</span>
        <textarea
          id={`${idp}-desc`}
          rows={3}
          value={value.description}
          placeholder="Optional description"
          onChange={(e) => set({ description: e.target.value })}
        />
      </label>
      <div className="field">
        <span>Color</span>
        <div className="swatches">
          {PRESET_COLORS.map((c) => (
            <button
              key={c}
              type="button"
              className={`swatch-btn${value.color_hex === c ? ' selected' : ''}`}
              style={{ background: c, color: c }}
              aria-label={`Color ${c}`}
              aria-pressed={value.color_hex === c}
              onClick={() => pickColor(c)}
            />
          ))}
        </div>
      </div>
      <div className="field">
        <label htmlFor={`${idp}-tags`}>Tags</label>
        <TagInput id={`${idp}-tags`} value={value.project_tags} onChange={(project_tags) => set({ project_tags })} />
        <span className="muted small">Press Enter to add a tag. Backspace removes the last tag.</span>
      </div>
      <ErrorText error={error} />
      <div className="actions">
        <button type="submit" disabled={!value.name.trim() || busy}>
          {busy ? 'Saving…' : submitLabel}
        </button>
        <button type="button" className="link" onClick={onCancel} disabled={busy}>
          Cancel
        </button>
      </div>
    </form>
  )
}

/** Delete moves the project to the trash; the first click arms the button. */
function DeleteButton({ busy, onConfirm }: { busy: boolean; onConfirm: () => void }) {
  const [armed, setArmed] = useState(false)
  if (!armed) {
    return (
      <button className="danger" disabled={busy} onClick={() => setArmed(true)}>
        Delete
      </button>
    )
  }
  return (
    <>
      <button className="danger armed" disabled={busy} onClick={onConfirm}>
        Confirm delete
      </button>
      <button className="link" disabled={busy} onClick={() => setArmed(false)}>
        Cancel
      </button>
    </>
  )
}

function ProjectCard({
  project,
  busy,
  onEdit,
  onAction,
}: {
  project: Project
  busy: boolean
  onEdit: () => void
  onAction: (action: 'archive' | 'restore' | 'delete') => void
}) {
  const tags = project.project_tags
  const n = project.paper_count ?? project.source_ids.length
  return (
    <li className="card project-card">
      <div className="project-name">
        <Swatch color={project.color_hex} />
        <strong>{project.name}</strong>
      </div>
      {project.description && (
        <div className="project-desc muted small">
          <MathText forceInline>{project.description}</MathText>
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
        {tags.length > 3 && <span className="muted small">+{tags.length - 3}</span>}
      </div>
      <div className="actions">
        {project.status === 'archived' ? (
          <button disabled={busy} onClick={() => onAction('restore')}>
            Restore
          </button>
        ) : (
          <>
            <button disabled={busy} onClick={onEdit}>
              Edit
            </button>
            <button disabled={busy} onClick={() => onAction('archive')}>
              Archive
            </button>
          </>
        )}
        <DeleteButton busy={busy} onConfirm={() => onAction('delete')} />
      </div>
    </li>
  )
}

export default function Projects() {
  const [showArchived, setShowArchived] = useState(false)
  const [projects, setProjects] = useState<Project[] | null>(null)
  const [archivedCount, setArchivedCount] = useState(0)
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<number | null>(null)
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const [list, archived] = await Promise.all([
        api.projects(showArchived ? 'archived' : 'active'),
        showArchived ? null : api.projects('archived'),
      ])
      setProjects(list)
      setArchivedCount(archived ? archived.length : list.length)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [showArchived])

  useEffect(() => {
    load()
  }, [load])

  const act = async (p: Project, action: 'archive' | 'restore' | 'delete') => {
    setBusy(p.id)
    setError('')
    try {
      if (action === 'archive') await api.archiveProject(p.id)
      else if (action === 'restore') await api.unarchiveProject(p.id)
      else await api.deleteProject(p.id)
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const create = async (value: ProjectInput) => {
    await api.createProject(value)
    setCreating(false)
    await load()
  }

  const save = async (p: Project, value: ProjectInput) => {
    await api.updateProject(p.id, value)
    setEditing(null)
    await load()
  }

  const switchView = (archived: boolean) => {
    setShowArchived(archived)
    setProjects(null)
    setCreating(false)
    setEditing(null)
  }

  return (
    <section>
      <div className="page-head">
        <h2>{showArchived ? 'Archived projects' : 'Projects'}</h2>
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
            New project
          </button>
        )}
      </div>
      <ErrorText error={error} />

      {creating && (
        <ProjectForm
          initial={EMPTY}
          submitLabel="Create"
          isEdit={false}
          onSubmit={create}
          onCancel={() => setCreating(false)}
        />
      )}

      {!projects ? (
        !error && <p className="muted">Loading…</p>
      ) : projects.length === 0 ? (
        <p className="muted">{showArchived ? 'No archived projects.' : 'No active projects.'}</p>
      ) : (
        <ul className="project-grid">
          {projects.map((p) =>
            editing === p.id ? (
              <li key={p.id}>
                <ProjectForm
                  initial={{
                    name: p.name,
                    description: p.description ?? '',
                    color_hex: p.color_hex,
                    project_tags: p.project_tags,
                  }}
                  submitLabel="Save"
                  isEdit
                  onSubmit={(v) => save(p, v)}
                  onCancel={() => setEditing(null)}
                />
              </li>
            ) : (
              <ProjectCard
                key={p.id}
                project={p}
                busy={busy !== null}
                onEdit={() => setEditing(p.id)}
                onAction={(a) => act(p, a)}
              />
            ),
          )}
        </ul>
      )}
      <p className="muted small">Deleted projects go to the Trash, where you can restore them.</p>
    </section>
  )
}
