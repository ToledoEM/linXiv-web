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
// A finished job's card stays this long, then it folds into the red dot.
const SHOW_MS = 5_000
const MAX_FINISHED = 20

// Maintenance operations (Settings → Server Admin) are `maint-<operation id>`.
const MAINT = 'maint-'
const info = (j: Job) =>
  JOB_INFO[j.kind] ??
  (j.kind.startsWith(MAINT)
    ? { label: `Maintenance: ${j.kind.slice(MAINT.length).replaceAll('-', ' ')}`, href: '/settings#admin' }
    : undefined)
const label = (j: Job) => info(j)?.label ?? j.kind
const progress = (j: Job) => (j.total > 0 ? `${j.done} / ${j.total}` : `${j.done}`)

const stateLabel = (j: Job) => (j.state === 'done' ? 'Done' : j.state === 'cancelled' ? 'Cancelled' : 'Failed')

/** Corner panel on every page: running background jobs with progress and Cancel.
 *  A job that finishes while it is watching shows its result for a few seconds,
 *  then folds into a red dot with a count; the dot opens the finished list
 *  (Dismiss, Dismiss all). */
export default function ActivityTray() {
  const [running, setRunning] = useState<Job[]>([])
  const [finished, setFinished] = useState<Job[]>([])
  // Finished jobs still shown as full cards (ids), before they fold into the dot.
  const [fresh, setFresh] = useState<Set<number>>(() => new Set())
  const [open, setOpen] = useState(false)
  const [error, setError] = useState('')
  const watched = useRef(new Set<number>())
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const fold = useCallback((id: number) => {
    timers.current.delete(id)
    setFresh((f) => {
      const next = new Set(f)
      next.delete(id)
      return next
    })
  }, [])

  const poll = useCallback(async () => {
    try {
      const jobs = await api.jobs()
      const now = jobs.filter((j) => j.state === 'running')
      const ended = jobs.filter((j) => j.state !== 'running' && watched.current.has(j.id))
      ended.forEach((j) => watched.current.delete(j.id))
      now.forEach((j) => watched.current.add(j.id))
      setRunning(now)
      if (ended.length) {
        setFinished((f) => [...ended, ...f].slice(0, MAX_FINISHED))
        setFresh((f) => new Set([...f, ...ended.map((j) => j.id)]))
        for (const j of ended) timers.current.set(j.id, setTimeout(() => fold(j.id), SHOW_MS))
      }
      setError('')
      return now.length > 0
    } catch (err) {
      setError((err as Error).message)
      return false
    }
  }, [fold])

  useEffect(() => {
    const pending = timers.current
    return () => pending.forEach((t) => clearTimeout(t))
  }, [])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  const dismiss = (ids: number[]) => {
    for (const id of ids) {
      clearTimeout(timers.current.get(id))
      timers.current.delete(id)
    }
    setFinished((f) => f.filter((j) => !ids.includes(j.id)))
    setFresh((f) => new Set([...f].filter((id) => !ids.includes(id))))
  }

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

  const cards = finished.filter((j) => fresh.has(j.id))
  const folded = finished.filter((j) => !fresh.has(j.id))
  const listOpen = open && folded.length > 0

  const finishedCard = (j: Job) => (
    <div key={j.id} className="tray-job">
      <div className="tray-head">
        <span>{label(j)}</span>
        <span className={`small ${j.state === 'done' ? 'success' : 'error'}`}>{stateLabel(j)}</span>
      </div>
      <div className="muted small">
        {progress(j)}
        {j.errors.length > 0 && ` · ${j.errors.length} error${j.errors.length === 1 ? '' : 's'}`}
        {j.error && ` · ${j.error}`}
      </div>
      <button type="button" className="link small" onClick={() => dismiss([j.id])}>
        Dismiss
      </button>
    </div>
  )

  return (
    <aside className="activity-tray" aria-label="Background jobs" aria-live="polite">
      {running.map((j) => (
        <div key={j.id} className="tray-job">
          <div className="tray-head">
            <Link to={info(j)?.href ?? '/settings'}>{label(j)}</Link>
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
      {cards.map(finishedCard)}
      {listOpen && (
        <div className="tray-finished-list" role="region" aria-label="Finished jobs">
          <div className="tray-head">
            <span className="small">Finished jobs</span>
            <button type="button" className="link small" onClick={() => dismiss(folded.map((j) => j.id))}>
              Dismiss all
            </button>
          </div>
          {folded.map(finishedCard)}
        </div>
      )}
      {folded.length > 0 && (
        <button
          type="button"
          className="tray-dot"
          aria-label={`${folded.length} finished job${folded.length === 1 ? '' : 's'}`}
          aria-expanded={listOpen}
          onClick={() => setOpen((o) => !o)}
        >
          {folded.length}
        </button>
      )}
      {error && <div className="error small">{error}</div>}
    </aside>
  )
}
