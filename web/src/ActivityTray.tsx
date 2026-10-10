import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from './api'
import type { Job } from './types'

/** Where each background job is started and explained (Settings cards). */
const JOB_INFO: Record<string, { label: string; href: string }> = {
  'index-sources': { label: 'TeX source index', href: '/settings#library' },
  'index-pdf-text': { label: 'PDF text index', href: '/settings#library' },
  'pdf-layout': { label: 'PDF folders', href: '/settings#library' },
}
const BUSY_POLL = 5_000
const IDLE_POLL = 30_000

const label = (j: Job) => JOB_INFO[j.kind]?.label ?? j.kind
const progress = (j: Job) => (j.total > 0 ? `${j.done} / ${j.total}` : `${j.done}`)

/** Corner panel on every page: running background jobs with progress and Cancel;
 *  jobs that finish while it is watching stay listed until dismissed. */
export default function ActivityTray() {
  const [running, setRunning] = useState<Job[]>([])
  const [finished, setFinished] = useState<Job[]>([])
  const [error, setError] = useState('')
  const watched = useRef(new Set<number>())

  const poll = useCallback(async () => {
    try {
      const jobs = await api.jobs()
      const now = jobs.filter((j) => j.state === 'running')
      const ended = jobs.filter((j) => j.state !== 'running' && watched.current.has(j.id))
      ended.forEach((j) => watched.current.delete(j.id))
      now.forEach((j) => watched.current.add(j.id))
      setRunning(now)
      if (ended.length) setFinished((f) => [...ended, ...f].slice(0, 5))
      setError('')
      return now.length > 0
    } catch (err) {
      setError((err as Error).message)
      return false
    }
  }, [])

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    let stopped = false
    const tick = async () => {
      const busy = document.visibilityState === 'visible' ? await poll() : false
      if (!stopped) timer = setTimeout(() => void tick(), busy ? BUSY_POLL : IDLE_POLL)
    }
    const wake = () => {
      if (document.visibilityState !== 'visible') return
      clearTimeout(timer)
      void tick()
    }
    void tick()
    // A job started on a Settings card shows up at once, not on the next idle poll.
    window.addEventListener('lxw-job-started', wake)
    document.addEventListener('visibilitychange', wake)
    return () => {
      stopped = true
      clearTimeout(timer)
      window.removeEventListener('lxw-job-started', wake)
      document.removeEventListener('visibilitychange', wake)
    }
  }, [poll])

  const cancel = async (id: number) => {
    try {
      await api.cancelJob(id)
      await poll()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (!running.length && !finished.length) return null

  return (
    <aside className="activity-tray" aria-label="Background jobs" aria-live="polite">
      {running.map((j) => (
        <div key={j.id} className="tray-job">
          <div className="tray-head">
            <Link to={JOB_INFO[j.kind]?.href ?? '/settings'}>{label(j)}</Link>
            <span className="muted small">{progress(j)}</span>
          </div>
          {j.total > 0 && <progress max={j.total} value={j.done} />}
          {j.current && <div className="muted small tray-current">{j.current}</div>}
          <button
            type="button"
            className="link small"
            disabled={j.cancel_requested}
            onClick={() => void cancel(j.id)}
          >
            {j.cancel_requested ? 'Stopping…' : 'Cancel'}
          </button>
        </div>
      ))}
      {finished.map((j) => (
        <div key={j.id} className="tray-job">
          <div className="tray-head">
            <span>{label(j)}</span>
            <span className={`small ${j.state === 'done' ? 'success' : 'error'}`}>
              {j.state === 'done' ? 'Done' : j.state === 'cancelled' ? 'Cancelled' : 'Failed'}
            </span>
          </div>
          <div className="muted small">
            {progress(j)}
            {j.errors.length > 0 && ` · ${j.errors.length} error${j.errors.length === 1 ? '' : 's'}`}
            {j.error && ` · ${j.error}`}
          </div>
          <button
            type="button"
            className="link small"
            onClick={() => setFinished((f) => f.filter((x) => x.id !== j.id))}
          >
            Dismiss
          </button>
        </div>
      ))}
      {error && <div className="error small">{error}</div>}
    </aside>
  )
}
