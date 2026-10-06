import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api'
import { ErrorText } from './components'

type Preview = {
  project_name: string
  description: string
  paper_count: number
  note_count: number
  annotation_count: number
  has_pdfs: boolean
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** Import a `.lxproj` archive (desktop ImportDialog, .lxproj part): pick a file,
 * read its summary, choose merge/overwrite, import into a NEW project. */
export default function ProjectImport({ onCancel }: { onCancel: () => void }) {
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Preview | null>(null)
  const [onConflict, setOnConflict] = useState<'merge' | 'overwrite'>('merge')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const pick = async (f: File | null) => {
    setFile(f)
    setPreview(null)
    setError('')
    if (!f) return
    setBusy(true)
    try {
      setPreview(await api.previewProjectImport(f))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const commit = async () => {
    if (!file) return
    setBusy(true)
    setError('')
    try {
      const { project_id } = await api.importProject(file, onConflict)
      navigate(`/projects/${project_id}`)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="card project-import">
      <label className="field">
        <span>Import project (.lxproj)</span>
        <input
          type="file"
          accept=".lxproj,application/zip"
          aria-label="Project archive"
          disabled={busy}
          onChange={(e) => pick(e.target.files?.[0] ?? null)}
        />
        <span className="muted small">Archives exported from linXiv (desktop or web). Imports always create a new project.</span>
      </label>
      {busy && !preview && <p className="muted small">Reading archive…</p>}
      {preview && (
        <div className="import-preview">
          <strong>{preview.project_name}</strong>
          {preview.description && <p className="muted small">{preview.description}</p>}
          <p className="small">
            {plural(preview.paper_count, 'paper')} · {plural(preview.note_count, 'note')}
            {preview.annotation_count > 0 && ` · ${plural(preview.annotation_count, 'highlight')}`}
            {preview.has_pdfs ? ' · includes PDFs' : ''}
          </p>
          <fieldset className="conflict-choice">
            <legend className="small">Papers already in your library</legend>
            <label className="check">
              <input type="radio" name="on-conflict" checked={onConflict === 'merge'} onChange={() => setOnConflict('merge')} />
              Merge: keep your stored metadata
            </label>
            <label className="check">
              <input
                type="radio"
                name="on-conflict"
                checked={onConflict === 'overwrite'}
                onChange={() => setOnConflict('overwrite')}
              />
              Overwrite: replace it with the archive's metadata
            </label>
          </fieldset>
        </div>
      )}
      <ErrorText error={error} />
      <div className="actions">
        <button type="button" disabled={!preview || busy} onClick={commit}>
          {busy && preview ? 'Importing…' : 'Import'}
        </button>
        <button type="button" className="link" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}
