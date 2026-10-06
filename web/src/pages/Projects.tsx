import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { ErrorText } from '../components'
import ProjectImport from '../ProjectImport'
import { DeleteButton, ProjectForm, Swatch } from '../projectParts'
import { MathText } from '../tex'
import type { Project, ProjectInput } from '../types'

const EMPTY: ProjectInput = { name: '', description: '', color_hex: null, project_tags: [] }

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
        <Link to={`/projects/${project.id}`}>
          <strong>{project.name}</strong>
        </Link>
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
  const [importing, setImporting] = useState(false)
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
    setImporting(false)
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
        {!showArchived && !creating && !importing && (
          <span className="page-head-action actions-inline">
            <button className="link" onClick={() => setImporting(true)}>
              Import…
            </button>
            <button onClick={() => setCreating(true)}>New project</button>
          </span>
        )}
      </div>
      <ErrorText error={error} />

      {importing && <ProjectImport onCancel={() => setImporting(false)} />}

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
