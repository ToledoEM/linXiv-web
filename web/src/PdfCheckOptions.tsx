import { useEffect, useState } from 'react'
import { api } from './api'
import { ErrorText } from './components'

/** "Check PDF files": top-level folders of the PDF folder the check counts but
 *  never lists as unlinked (e.g. dup, errors). Comma separated; saved on Save.
 *  orphans/ is always skipped. */
export default function PdfCheckOptions() {
  const [saved, setSaved] = useState<string[] | null>(null)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    api
      .pdfCheckOptions()
      .then((o) => {
        setSaved(o.skip)
        setDraft(o.skip.join(', '))
      })
      .catch((err) => setError((err as Error).message))
  }, [])

  if (saved === null) return error ? <ErrorText error={error} /> : null

  const names = draft
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
  const changed = names.join(',') !== saved.join(',')

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      const o = await api.setPdfCheckOptions(names)
      setSaved(o.skip)
      setDraft(o.skip.join(', '))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="small"
      onSubmit={(e) => {
        e.preventDefault()
        void save()
      }}
    >
      <label className="check">
        Skip folders
        <input
          type="text"
          className="skip-input"
          aria-label="Folders the PDF check skips"
          placeholder="dup, errors"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
        />
      </label>{' '}
      <button type="submit" disabled={busy || !changed}>
        Save
      </button>
      <span className="muted"> Folders directly in the PDF folder, comma separated. orphans/ is always skipped.</span>
      <ErrorText error={error} />
    </form>
  )
}
