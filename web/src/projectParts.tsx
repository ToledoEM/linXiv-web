import { useEffect, useState, type FormEvent, type KeyboardEvent } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import { failedMessage, hasTag, PRESET_COLORS, READING_LIST_TAG } from './projects'
import type { Project, ProjectInput } from './types'

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

export function Swatch({ color }: { color: string | null }) {
  return <span className="swatch" style={{ background: color ?? 'var(--accent)' }} />
}

export function ProjectForm({
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
export function DeleteButton({ busy, onConfirm }: { busy: boolean; onConfirm: () => void }) {
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

/** Add the selected papers to an existing or new project (desktop Library SelectionBar); `selected` holds source_ids. */
export function AddToProjectBar({
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
