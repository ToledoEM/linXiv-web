import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { Job } from './types'

const KIND = 'index-sources'
const LIMITS = [10, 25, 50, 100]
const POLL_MS = 1500

/** Backfill full-text search: fetch arXiv TeX source for papers that lack it, as a background job. */
export default function FullTextIndex() {
  const [pending, setPending] = useState<{ pending: number; arxiv_papers: number } | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [limit, setLimit] = useState(25)
  const [error, setError] = useState('')

  const loadPending = useCallback(() => {
    api
      .sourcesPending()
      .then(setPending)
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
      setJob(await api.startIndexSources(limit))
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
      <h3>Full-text index</h3>
      <p className="muted small">
        Fetches the LaTeX source that authors uploaded to arXiv and indexes its text, so the Library search
        finds words inside papers. Papers are fetched about 7 seconds apart to respect arXiv&apos;s rate limit; the
        rest of the app stays usable meanwhile.
      </p>
      {pending && (
        <p className="small">
          {pending.pending} of {pending.arxiv_papers} arXiv paper{pending.arxiv_papers === 1 ? '' : 's'} not indexed yet.
        </p>
      )}
      <div className="actions">
        <label className="check">
          Papers per run
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} disabled={running}>
            {LIMITS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        {running ? (
          <button type="button" className="danger" onClick={cancel} disabled={job?.cancel_requested}>
            {job?.cancel_requested ? 'Stopping…' : 'Stop'}
          </button>
        ) : (
          <button type="button" onClick={start} disabled={!pending?.pending}>
            Index now
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
                    {job.done} of {job.total} · {job.current ? <span className="mono">{job.current}</span> : 'waiting between arXiv requests…'}
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
              {job.result.skipped ?? 0} without TeX source, {job.result.failed ?? 0} failed
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
