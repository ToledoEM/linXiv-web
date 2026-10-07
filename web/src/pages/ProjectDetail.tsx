import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, idPath, projectExportUrl, type ExportFormat } from '../api'
import { ErrorText, SortHeader } from '../components'
import { loadSort, nextSort, parsePaperSort, saveSort, sortPapers, type PaperSortKey } from '../paperSort'
import { DeleteButton, ProjectForm, Swatch } from '../projectParts'
import { failedMessage, READING_LIST_TAG, toggled } from '../projects'
import { MathText } from '../tex'
import type { Paper, Project, ProjectInput } from '../types'

/** Pick library papers not yet in the project (desktop AddPapersDialog). */
function AddPapers({
  projectId,
  existing,
  onAdded,
  onClose,
}: {
  projectId: number
  existing: string[]
  onAdded: () => Promise<void>
  onClose: () => void
}) {
  const [library, setLibrary] = useState<Paper[] | null>(null)
  const [q, setQ] = useState('')
  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .papers({ limit: 1000, sort: 'added', dir: 'desc' })
      .then(setLibrary)
      .catch((err) => setError((err as Error).message))
  }, [])

  const candidates = useMemo(() => (library ?? []).filter((p) => !existing.includes(p.source_id)), [library, existing])
  const needle = q.trim().toLowerCase()
  const shown = needle
    ? candidates.filter((p) => p.title.toLowerCase().includes(needle) || p.source_id.toLowerCase().includes(needle))
    : candidates

  const add = async () => {
    const ids = [...picked]
    if (!ids.length || busy) return
    setBusy(true)
    setError('')
    try {
      const r = await api.addProjectPapers(projectId, ids)
      await onAdded()
      if (r.failed.length) {
        // Keep only the failures selected so a retry can't re-add the rest.
        setPicked(new Set(r.failed))
        setError(failedMessage(r.failed.length, ids.length))
      } else {
        onClose()
      }
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card add-papers">
      <input placeholder="Search papers…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus />
      <div className="pick-list">
        {!library ? (
          !error && <p className="muted small">Loading…</p>
        ) : shown.length === 0 ? (
          <p className="muted small">
            {candidates.length === 0
              ? 'All library papers are already in this project.'
              : 'No papers match your search.'}
          </p>
        ) : (
          shown.map((p) => (
            <label key={p.source_id} className="pick-row">
              <input
                type="checkbox"
                checked={picked.has(p.source_id)}
                onChange={() => setPicked((s) => toggled(s, p.source_id))}
              />
              <span>
                <MathText forceInline>{p.title}</MathText>
                <span className="muted small block">{p.authors?.join(', ') || p.source_id}</span>
              </span>
            </label>
          ))
        )}
      </div>
      <ErrorText error={error} />
      <div className="actions">
        <button onClick={add} disabled={!picked.size || busy}>
          {busy ? 'Adding…' : 'Add'}
        </button>
        <button className="link" onClick={onClose} disabled={busy}>
          Cancel
        </button>
        {picked.size > 0 && <span className="muted small">{picked.size} selected</span>}
      </div>
    </div>
  )
}

const EXPORTS: { format: ExportFormat; label: string }[] = [
  { format: 'bibtex', label: 'BibTeX' },
  { format: 'obsidian', label: 'Obsidian' },
  { format: 'zotero', label: 'Zotero' },
  { format: 'lxproj', label: '.lxproj' },
]

/** Export downloads (desktop ExportDialog). */
function ExportPanel({ projectId, onClose }: { projectId: number; onClose: () => void }) {
  const [pdfs, setPdfs] = useState(false)
  return (
    <div className="card export-panel">
      <label className="check">
        <input type="checkbox" checked={pdfs} onChange={(e) => setPdfs(e.target.checked)} />
        Include PDFs in .lxproj archive
      </label>
      <p className="muted small">BibTeX, Obsidian and Zotero exports include paper metadata only.</p>
      <div className="actions">
        {EXPORTS.map((e) => (
          <a key={e.format} className="button" href={projectExportUrl(projectId, e.format, pdfs)} download>
            ⇩ {e.label}
          </a>
        ))}
        <button className="link" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  )
}

// One choice for every project and reading list; none = project order.
const SORT_KEY = 'lxw.projectSort'

export default function ProjectDetail() {
  const { id } = useParams()
  const projectId = id && /^\d+$/.test(id) ? Number(id) : NaN
  const navigate = useNavigate()
  const [project, setProject] = useState<Project | null>(null)
  const [papers, setPapers] = useState<Paper[] | null>(null)
  const [loadError, setLoadError] = useState('')
  const [error, setError] = useState('')
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [busy, setBusy] = useState(false)
  const [sort, setSort] = useState(() => loadSort(SORT_KEY, parsePaperSort, null))

  useEffect(() => saveSort(SORT_KEY, sort), [sort])
  const shown = useMemo(() => (papers ? sortPapers(papers, sort) : null), [papers, sort])

  const load = useCallback(async () => {
    if (Number.isNaN(projectId)) {
      setLoadError('Project not found')
      return
    }
    try {
      const [p, list] = await Promise.all([api.project(projectId), api.projectPapers(projectId)])
      setProject(p)
      setPapers(list)
    } catch (err) {
      setLoadError((err as Error).message)
    }
  }, [projectId])

  useEffect(() => {
    load()
  }, [load])

  const run = async (fn: () => Promise<unknown>, after?: () => void) => {
    setBusy(true)
    setError('')
    try {
      await fn()
      if (after) after()
      else await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const removeSelected = async () => {
    const ids = [...selected]
    setBusy(true)
    setError('')
    const results = await Promise.allSettled(ids.map((sid) => api.removeProjectPaper(projectId, sid)))
    const failed = ids.filter((_, i) => results[i].status === 'rejected')
    await load()
    setSelected(new Set(failed))
    if (failed.length) setError(`Failed to remove ${failed.length} paper${failed.length === 1 ? '' : 's'}`)
    setBusy(false)
  }

  const save = async (value: ProjectInput) => {
    await api.updateProject(projectId, value)
    setEditing(false)
    await load()
  }

  if (loadError) {
    return (
      <section>
        <p className="small">
          <Link to="/projects">← Projects</Link>
        </p>
        <ErrorText error={loadError} />
      </section>
    )
  }
  if (!project || !papers || !shown) return <p className="muted">Loading…</p>

  const tags = project.project_tags.filter((t) => t.toLowerCase() !== READING_LIST_TAG)
  const allSelected = papers.length > 0 && papers.every((p) => selected.has(p.source_id))

  return (
    <section>
      <p className="small">
        <Link to="/projects">← Projects</Link>
      </p>
      {editing ? (
        <ProjectForm
          initial={{
            name: project.name,
            description: project.description ?? '',
            color_hex: project.color_hex,
            project_tags: project.project_tags,
          }}
          submitLabel="Save"
          isEdit
          onSubmit={save}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          <div className="page-head">
            <h2 className="project-title">
              <Swatch color={project.color_hex} />
              {project.name}
            </h2>
            {project.status === 'archived' && <span className="pill">Archived</span>}
            <div className="actions page-head-action">
              <button onClick={() => setExporting((v) => !v)} aria-expanded={exporting}>
                Export
              </button>
              {project.status === 'archived' ? (
                <button disabled={busy} onClick={() => run(() => api.unarchiveProject(projectId))}>
                  Restore
                </button>
              ) : (
                <>
                  <button disabled={busy} onClick={() => setEditing(true)}>
                    Edit
                  </button>
                  <button
                    disabled={busy}
                    onClick={() =>
                      run(
                        () => api.archiveProject(projectId),
                        () => navigate('/projects'),
                      )
                    }
                  >
                    Archive
                  </button>
                </>
              )}
              <DeleteButton
                busy={busy}
                onConfirm={() =>
                  run(
                    () => api.deleteProject(projectId),
                    () => navigate('/projects'),
                  )
                }
              />
            </div>
          </div>
          {project.description && (
            <p className="muted abstract">
              <MathText>{project.description}</MathText>
            </p>
          )}
          {tags.length > 0 && (
            <div className="tags">
              {tags.map((t) => (
                <span key={t} className="pill pill-tag">
                  {t}
                </span>
              ))}
            </div>
          )}
        </>
      )}
      {exporting && !editing && <ExportPanel projectId={projectId} onClose={() => setExporting(false)} />}
      <ErrorText error={error} />

      <div className="section-head">
        <h3>Papers in this project</h3>
        {!adding && <button onClick={() => setAdding(true)}>Add papers</button>}
      </div>
      {adding && (
        <AddPapers
          projectId={projectId}
          existing={project.source_ids}
          onAdded={load}
          onClose={() => setAdding(false)}
        />
      )}

      {selected.size > 0 && (
        <div className="selection-bar">
          <span>
            {selected.size} paper{selected.size === 1 ? '' : 's'} selected
          </span>
          <span className="grow" />
          <button className="link" onClick={() => setSelected(new Set())} disabled={busy}>
            Clear
          </button>
          <button className="danger" onClick={removeSelected} disabled={busy}>
            {busy ? 'Removing…' : 'Remove from project'}
          </button>
        </div>
      )}

      {papers.length === 0 ? (
        <p className="muted">No papers in this project. Add papers from your library to start organizing it.</p>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="check-col">
                  <input
                    type="checkbox"
                    aria-label="Select all"
                    checked={allSelected}
                    onChange={() => setSelected(allSelected ? new Set() : new Set(papers.map((p) => p.source_id)))}
                  />
                </th>
                {(
                  [
                    ['title', 'Title'],
                    ['authors', 'Authors'],
                    ['published', 'Published'],
                    ['category', 'Category'],
                    ['tags', 'Tags'],
                    ['pdf', 'PDF'],
                  ] as [PaperSortKey, string][]
                ).map(([key, label]) => (
                  <SortHeader
                    key={key}
                    label={label}
                    dir={sort?.key === key ? sort.dir : null}
                    onClick={() => setSort((s) => nextSort(s, key))}
                  />
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((p) => (
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
                    <Link to={`/paper/${idPath(p.source_id)}`} state={{ fromProjectId: projectId }}>
                      <MathText forceInline>{p.title}</MathText>
                    </Link>
                    <div className="muted small mono">{p.source_id}</div>
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
