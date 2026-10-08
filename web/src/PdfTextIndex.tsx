import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { Job } from './types'

const KIND = 'index-pdf-text'
const POLL_MS = 1500

/** Full-text search for papers arXiv has no TeX for: index the saved PDFs' text, as a background job. */
export default function PdfTextIndex() {
  const [pending, setPending] = useState<number | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [error, setError] = useState('')

  const loadPending = useCallback(() => {
    api
      .sourcesPending()
      .then((p) => setPending(p.pdf_pending))
      .catch((err) => setError((err as Error).message))
  }, [])

  // Pick up the latest job, so a reload shows one still running.
  useEffect(() => {
    loadPending()
    api
      .jobs(KIND)
      .then((jobs) => setJob(jobs[0] ?? null))
      .catch(() => {})
  }, [loadPending])

  const running = job?.state === 'running'
  const jobId = job?.id

  useEffect(() => {
    if (!running || jobId === undefined) return
    const t = setInterval(() => {
      api
        .job(jobId)
        .then((j) => {
          setJob(j)
          if (j.state !== 'running') loadPending()
        })
        .catch((err) => setError((err as Error).message))
    }, POLL_MS)
    return () => clearInterval(t)
  }, [running, jobId, loadPending])

  const start = async () => {
    setError('')
    try {
      setJob(await api.startIndexPdfText())
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const cancel = async () => {
    if (!job) return
    try {
      setJob(await api.cancelJob(job.id))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const pct = job && job.total ? Math.round((100 * job.done) / job.total) : 0

  return (
    <div className="card settings-section">
      <h3>PDF full text</h3>
      <p className="muted small">
        For papers that aren&apos;t on arXiv (DOI, PubMed, bioRxiv, imported PDFs): reads the text of each saved PDF on
        the server and indexes it, so the Library search finds words inside them. The text is stored in the library
        database; nothing leaves the server. Scanned PDFs without a text layer can&apos;t be indexed and are listed as
        failures.
      </p>
      {pending !== null && (
        <p className="small">
          {pending} paper{pending === 1 ? '' : 's'} with a PDF not indexed yet.
        </p>
      )}
      <div className="actions">
        {running ? (
          <button type="button" className="danger" onClick={cancel} disabled={job?.cancel_requested}>
            {job?.cancel_requested ? 'Stopping…' : 'Stop'}
          </button>
        ) : (
          <button type="button" onClick={start} disabled={!pending}>
            Index PDFs now
          </button>
        )}
      </div>
      <ErrorText error={error} />
      {job && (
        <div className="job">
          {running && (
            <>
              <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                <span style={{ width: `${pct}%` }} />
              </div>
              <p className="muted small">
                {job.total ? (
                  <>
                    {job.done} of {job.total}
                    {job.current && (
                      <>
                        {' '}
                        · <span className="mono">{job.current}</span>
                      </>
                    )}
                  </>
                ) : (
                  'Finding papers to index…'
                )}
              </p>
            </>
          )}
          {!running && (
            <p className="small">
              Last run {job.state === 'done' ? 'finished' : job.state}: {job.result.indexed ?? 0} indexed,{' '}
              {job.result.failed ?? 0} failed
              {job.total ? ` (${job.done} of ${job.total} papers)` : ''}.
            </p>
          )}
          <ErrorText error={job.error ?? undefined} />
          {job.errors.length > 0 && (
            <details>
              <summary>
                {job.errors.length} failure{job.errors.length === 1 ? '' : 's'}
              </summary>
              <ul className="plain small">
                {job.errors.map((e) => (
                  <li key={e.source_id}>
                    <span className="mono">{e.source_id}</span>: {e.error}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}
    </div>
  )
}
