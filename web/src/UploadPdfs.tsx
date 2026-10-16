import { useState, type DragEvent, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, paperPath } from './api'
import { ErrorText } from './components'
import { MathText } from './tex'

type Result = { name: string; source_id?: string; title?: string; error?: string }

const isPdf = (f: File) => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf')

/** Add paper page section: upload PDF files from this computer. */
export default function UploadPdfs() {
  const [files, setFiles] = useState<File[]>([])
  const [results, setResults] = useState<Result[]>([])
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [skipped, setSkipped] = useState(0)
  const [pickerKey, setPickerKey] = useState(0)

  /** Add to the selection (drops and picks accumulate); same name + size counted once. */
  const add = (incoming: File[]) => {
    const pdfs = incoming.filter(isPdf)
    setSkipped(incoming.length - pdfs.length)
    setFiles((cur) => {
      const seen = new Set(cur.map((f) => `${f.name}:${f.size}`))
      return [...cur, ...pdfs.filter((f) => !seen.has(`${f.name}:${f.size}`))]
    })
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    if (!busy) add(Array.from(e.dataTransfer.files))
  }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    const out: Result[] = []
    // One at a time: the server serializes linxiv calls anyway.
    for (const f of files) {
      try {
        const r = await api.importPdf(f)
        out.push({ name: f.name, ...r })
      } catch (err) {
        out.push({ name: f.name, error: (err as Error).message })
      }
      setResults([...out])
    }
    setBusy(false)
    setFiles([])
    setSkipped(0)
    setPickerKey((k) => k + 1)
  }

  return (
    <>
      <h3>Upload PDF files</h3>
      <p className="muted">
        PDF files from this computer. linXiv reads the metadata from each PDF and adds the paper with its PDF to the
        library.
      </p>
      <form onSubmit={submit}>
        <div
          className={`drop-zone${dragging ? ' dragging' : ''}`}
          data-testid="drop-zone"
          onDragOver={(e) => {
            e.preventDefault()
            e.dataTransfer.dropEffect = 'copy'
            setDragging(true)
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <p>Drop PDF files here, or choose them:</p>
          <input
            key={pickerKey}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            aria-label="PDF files"
            onChange={(e) => add(Array.from(e.target.files ?? []))}
          />
        </div>
        {skipped > 0 && (
          <p className="muted small">
            {skipped} file{skipped === 1 ? '' : 's'} skipped: not a PDF.
          </p>
        )}
        {files.length > 0 && (
          <div className="card">
            <strong>
              {files.length} PDF{files.length === 1 ? '' : 's'} selected
            </strong>
            <ul className="small">
              {files.map((f) => (
                <li key={`${f.name}:${f.size}`}>{f.name}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="actions">
          <button disabled={busy || files.length === 0}>{busy ? 'Uploading…' : 'Upload'}</button>
          {files.length > 0 && !busy && (
            <button
              type="button"
              className="link"
              onClick={() => {
                setFiles([])
                setSkipped(0)
                setPickerKey((k) => k + 1)
              }}
            >
              Clear selection
            </button>
          )}
        </div>
      </form>
      <ul className="results">
        {results.map((r, i) => (
          <li key={i} className="card">
            <strong>{r.name}</strong>
            {r.source_id && (
              <div>
                <Link to={paperPath(r.source_id)}>
                  <MathText forceInline>{r.title || r.source_id}</MathText>
                </Link>
              </div>
            )}
            <ErrorText error={r.error} />
          </li>
        ))}
      </ul>
    </>
  )
}
