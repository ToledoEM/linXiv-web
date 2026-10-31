import { useCallback, useEffect, useState } from 'react'
import { api, unlinkedCsvUrl } from './api'
import { ErrorText } from './components'
import ConfirmDialog from './ConfirmDialog'
import { formatBytes } from './format'
import type { Job, PdfCheckReport as Report } from './types'

const POLL_MS = 1000
const n = (v: number | undefined) => (v ?? 0).toLocaleString()

/** "Check PDF files" result per library, loaded when opened: what is on disk next
 *  to the paper counts, missing and unlinked files, the full unlinked list as CSV,
 *  and "Move to orphans/". Papers are listed by id, not linked: they may belong to
 *  another account's library. */
export default function PdfCheckReport() {
  const [reports, setReports] = useState<Report[] | null>(null)
  const [error, setError] = useState('')
  const [confirm, setConfirm] = useState<Report | null>(null)
  const [moving, setMoving] = useState<Job | null>(null)
  const [moved, setMoved] = useState<Record<string, Job>>({})

  const fetchReports = useCallback(
    () =>
      api
        .pdfCheck()
        .then((r) => setReports(r.libraries))
        .catch((err) => setError((err as Error).message)),
    [],
  )

  const load = (open: boolean) => {
    if (open && !reports) void fetchReports()
  }

  const movingId = moving?.id
  useEffect(() => {
    if (movingId === undefined) return
    const t = setInterval(() => {
      api
        .job(movingId)
        .then((job) => {
          if (job.state === 'running') {
            setMoving(job)
            return
          }
          setMoving(null)
          setMoved((m) => ({ ...m, [job.library ?? '']: job }))
          void fetchReports()
        })
        .catch((err) => {
          setMoving(null)
          setError((err as Error).message)
        })
    }, POLL_MS)
    return () => clearInterval(t)
  }, [movingId, fetchReports])

  const move = async (r: Report) => {
    setConfirm(null)
    setError('')
    try {
      setMoving({ ...(await api.moveOrphans(r.library)), library: r.library })
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <details className="small" onToggle={(e) => load(e.currentTarget.open)}>
      <summary>Show report</summary>
      <ErrorText error={error} />
      {reports?.length === 0 && <p className="muted">No report yet.</p>}
      {reports?.map((r) => {
        const done = moved[r.library]
        return (
          <div key={r.library} className="pdf-check">
            <strong className="mono">{r.library}</strong>{' '}
            <span className="muted">
              {r.pdfs} PDFs · {r.missing_count} missing · {r.unlinked_count} unlinked
            </span>
            {r.disk && <Breakdown r={r} />}
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
            {r.unlinked_count > 0 && (
              <div className="actions">
                <a href={unlinkedCsvUrl(r.library)} download>
                  Download full list (CSV)
                </a>
                <button
                  type="button"
                  disabled={moving !== null}
                  onClick={() => setConfirm(r)}
                  aria-label={`Move unlinked files of ${r.library} to orphans`}
                >
                  Move {n(r.unlinked_count)} unlinked files to orphans/
                </button>
              </div>
            )}
            {moving?.library === r.library && (
              <div>
                Moving {moving.done} / {moving.total}
                {moving.current ? ` · ${moving.current}` : ''}
              </div>
            )}
            {done && (
              <div>
                Moved {n(done.result.moved)} to orphans/
                {done.result.skipped_recent ? ` · ${n(done.result.skipped_recent)} changed in the last hour, left` : ''}
                {done.result.failed ? ` · ${n(done.result.failed)} failed` : ''}
                {done.state === 'failed' && done.error ? ` · ${done.error}` : ''}
              </div>
            )}
          </div>
        )
      })}
      <ConfirmDialog
        open={confirm !== null}
        title="Move unlinked files to orphans/?"
        confirmLabel="Move"
        onConfirm={() => confirm && void move(confirm)}
        onCancel={() => setConfirm(null)}
      >
        <p>
          The PDF folder of <span className="mono">{confirm?.library}</span> is checked again, then each PDF no paper
          points at moves to <span className="mono">orphans/</span> under the same path. Files changed in the last hour
          and skipped folders stay. Nothing is deleted.
        </p>
      </ConfirmDialog>
    </details>
  )
}

/** Files on disk next to the paper counts, so the two numbers add up. */
function Breakdown({ r }: { r: Report }) {
  const disk = r.disk!
  return (
    <div className="table-wrap">
      <table className="pdf-check-breakdown">
        <tbody>
          <tr>
            <th scope="row">Files on disk</th>
            <td className="num">{n(disk.files)}</td>
            <td className="muted">
              {n(disk.pdf_files)} PDFs, {n(disk.other_files)} other files
              {disk.skipped_files ? `, ${n(disk.skipped_files)} in skipped folders (${(r.skip ?? []).join(', ')})` : ''}
            </td>
          </tr>
          <tr>
            <th scope="row">Papers</th>
            <td className="num">{n(r.papers)}</td>
            <td className="muted">
              {n(r.papers_with_pdf)} with a PDF; {n(r.extra_versions)} extra version files; {n(r.trashed_pdfs)} PDFs of
              papers in the trash
            </td>
          </tr>
          {disk.by_folder.map((f) => (
            <tr key={f.folder}>
              <td className="mono">{f.folder === '.' ? '(top level)' : `${f.folder}/`}</td>
              <td className="num">{n(f.files)}</td>
              <td className="muted">
                {n(f.pdfs)} PDFs{f.skipped ? ' · skipped' : f.unlinked ? ` · ${n(f.unlinked)} unlinked` : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
