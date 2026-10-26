import { useState } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import { formatBytes } from './format'
import type { PdfCheckReport as Report } from './types'

/** "Check PDF files" result per library, loaded when opened. Papers are listed
 *  by id, not linked: they may belong to another account's library. */
export default function PdfCheckReport() {
  const [reports, setReports] = useState<Report[] | null>(null)
  const [error, setError] = useState('')

  const load = (open: boolean) => {
    if (!open || reports) return
    api
      .pdfCheck()
      .then((r) => setReports(r.libraries))
      .catch((err) => setError((err as Error).message))
  }

  return (
    <details className="small" onToggle={(e) => load(e.currentTarget.open)}>
      <summary>Show report</summary>
      <ErrorText error={error} />
      {reports?.length === 0 && <p className="muted">No report yet.</p>}
      {reports?.map((r) => (
        <div key={r.library} className="pdf-check">
          <strong className="mono">{r.library}</strong>{' '}
          <span className="muted">
            {r.pdfs} PDFs · {r.missing_count} missing · {r.unlinked_count} unlinked
          </span>
          {r.missing.length > 0 && (
            <>
              <div>Papers whose PDF file is missing:</div>
              <ul className="plain">
                {r.missing.map((m) => (
                  <li key={`${m.source_id}-${m.version}`}>
                    {m.title || m.source_id}{' '}
                    <span className="muted mono">
                      {m.source_id} v{m.version}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {r.unlinked.length > 0 && (
            <>
              <div>Files no paper points at:</div>
              <ul className="plain mono">
                {r.unlinked.map((u) => (
                  <li key={u.file}>
                    {u.file} <span className="muted">{formatBytes(u.size)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {(r.missing.length < r.missing_count || r.unlinked.length < r.unlinked_count) && (
            <p className="muted">Lists cut to the first {Math.max(r.missing.length, r.unlinked.length)} entries.</p>
          )}
        </div>
      ))}
    </details>
  )
}
