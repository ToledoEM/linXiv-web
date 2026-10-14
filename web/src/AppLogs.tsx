import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, logsExportUrl } from './api'
import { ErrorText } from './components'
import ConfirmDialog from './ConfirmDialog'
import type { LogLevel, LogsResponse, LogWindow } from './types'

const LEVELS: { value: LogLevel; label: string }[] = [
  { value: 'debug', label: 'Debug (also every linxiv CLI call)' },
  { value: 'info', label: 'Info (requests, jobs, start/stop)' },
  { value: 'warning', label: 'Warning (failures only)' },
  { value: 'error', label: 'Error' },
]

const WINDOWS: { value: LogWindow; label: string }[] = [
  { value: '1h', label: 'Last hour' },
  { value: '24h', label: 'Last 24 hours' },
  { value: '7d', label: 'Last 7 days' },
  { value: '30d', label: 'Last 30 days' },
  { value: 'all', label: 'All' },
]

const LIMIT = 1000

const kb = (bytes: number) => `${(bytes / 1024).toFixed(1)} KB`

/** Settings → Server & data → Logs: level (saved with the card), viewer, export, clear. */
export default function AppLogs({
  level,
  onLevel,
  footer,
}: {
  level: LogLevel
  onLevel: (level: LogLevel) => void
  footer: ReactNode
}) {
  const [span, setSpan] = useState<LogWindow>('24h')
  const [data, setData] = useState<LogsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [armed, setArmed] = useState(false)
  const view = useRef<HTMLPreElement>(null)

  // Callers that reload on demand set `loading` first; the effect starts with it set.
  const load = useCallback(
    (w: LogWindow) =>
      api
        .logs(w, LIMIT)
        .then(
          (d) => {
            setData(d)
            setError('')
          },
          (err: Error) => setError(err.message),
        )
        .finally(() => setLoading(false)),
    [],
  )

  const reload = () => {
    setLoading(true)
    return load(span)
  }

  useEffect(() => {
    void load(span)
  }, [load, span])

  // Newest lines are at the bottom: show them first.
  useEffect(() => {
    if (view.current) view.current.scrollTop = view.current.scrollHeight
  }, [data])

  const clear = async () => {
    setArmed(false)
    try {
      await api.clearLogs()
      await reload()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const size = data?.files.reduce((n, f) => n + f.size, 0) ?? 0

  return (
    <div className="card settings-section">
      <h3>Logs</h3>
      <p className="muted small">
        Server log, kept in <span className="mono">logs/</span> in the data directory (5 MB × 4 files, oldest dropped)
        and printed to the container output (<span className="mono">docker logs</span>). Times are UTC.
      </p>
      <label className="field">
        <span>Log level</span>
        <select value={level} onChange={(e) => onLevel(e.target.value as LogLevel)}>
          {LEVELS.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
      {footer}

      <div className="toolbar">
        <select
          aria-label="Time window"
          value={span}
          onChange={(e) => {
            const w = WINDOWS.find((x) => x.value === e.target.value)?.value
            if (!w) return
            setLoading(true)
            setSpan(w)
          }}
        >
          {WINDOWS.map((w) => (
            <option key={w.value} value={w.value}>
              {w.label}
            </option>
          ))}
        </select>
        <button type="button" disabled={loading} onClick={() => void reload()}>
          {loading ? 'Loading…' : 'Refresh'}
        </button>
        <a className="button" href={logsExportUrl(span)} download>
          Download
        </a>
        <button type="button" className="danger" onClick={() => setArmed(true)}>
          Clear logs
        </button>
      </div>
      <ConfirmDialog
        open={armed}
        title="Clear the server log?"
        phrase="clear logs"
        confirmLabel="Clear logs"
        onConfirm={() => void clear()}
        onCancel={() => setArmed(false)}
      >
        <p>Every log file in the data directory is emptied. Download it first if you may need it.</p>
      </ConfirmDialog>
      <ErrorText error={error} />
      {data && (
        <>
          <span className="muted small">
            {data.lines.length} lines
            {data.truncated && ` (last ${LIMIT}; Download has the whole window)`} · {kb(size)} on disk
          </span>
          <pre ref={view} className="mono log-view">
            {data.lines.length ? data.lines.join('\n') : 'No log lines in this window.'}
          </pre>
        </>
      )}
    </div>
  )
}
