import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from './api'
import { ErrorText } from './components'
import ConfirmDialog from './ConfirmDialog'
import PdfCheckReport from './PdfCheckReport'
import ServerBackups from './ServerBackups'
import { runSummary } from './maintenance'
import type { MaintenanceOp, MaintenanceOverview } from './types'

const POLL_MS = 1000
const HOURS = Array.from({ length: 24 }, (_, h) => h)
const pad = (n: number) => String(n).padStart(2, '0')
// Pages that show what an operation found, for the library in view.
const REPORT_PAGES: Record<string, { to: string; label: string } | undefined> = {
  duplicates: { to: '/duplicates', label: 'Show duplicates' },
  'complete-metadata': { to: '/library?review=metadata', label: 'Review papers left incomplete' },
}

const when = (iso: string) => iso.replace('T', ' ').slice(0, 16)

/** Settings → Server Admin: operations that run over every library on the server,
 *  on demand (Run) or each night at the chosen hour. */
export default function MaintenanceSettings() {
  const [data, setData] = useState<MaintenanceOverview | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirm, setConfirm] = useState<MaintenanceOp | null>(null)

  const load = useCallback(() => {
    api
      .maintenance()
      .then(setData)
      .catch((err) => setError((err as Error).message))
  }, [])
  useEffect(load, [load])

  const busy = data?.ops.some((o) => o.job) ?? false
  useEffect(() => {
    if (!busy) return
    const t = setInterval(load, POLL_MS)
    return () => clearInterval(t)
  }, [busy, load])

  const saveSchedule = async (hour: number, nightly: string[], keep?: number) => {
    if (!data) return
    setSaving(true)
    setError('')
    try {
      const s = await api.setMaintenanceSchedule(hour, nightly, keep)
      setData({ ...data, ...s })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const run = async (op: MaintenanceOp) => {
    setConfirm(null)
    setError('')
    try {
      await api.runMaintenance(op.id)
    } catch (err) {
      setError((err as Error).message)
    }
    load()
  }

  const cancel = async (jobId: number) => {
    try {
      await api.cancelJob(jobId)
    } catch (err) {
      setError((err as Error).message)
    }
    load()
  }

  if (!data) return error ? <ErrorText error={error} /> : <p className="muted">Loading…</p>

  return (
    <div className="card settings-section">
      <h3>Maintenance operations</h3>
      <p className="muted small">
        Each operation runs over every library on the server. Tick &quot;Nightly&quot; to run it once a night.
      </p>
      <div className="actions">
        <label className="check">
          Nightly at
          <select
          aria-label="Nightly hour"
          value={data.hour}
          disabled={saving}
          onChange={(e) => void saveSchedule(Number(e.target.value), data.nightly)}
        >
          {HOURS.map((h) => (
            <option key={h} value={h}>
              {pad(h)}:00
            </option>
          ))}
          </select>
        </label>
        <span className="muted small">server time{data.timezone ? ` (${data.timezone})` : ''}</span>
      </div>
      {data.ops.length === 0 ? (
        <p className="muted">No operations available.</p>
      ) : (
        <div className="table-wrap">
          <table className="users-table maint-table">
            <tbody>
              {data.ops.map((op) => {
                const nightly = data.nightly.includes(op.id)
                const report = REPORT_PAGES[op.id]
                return (
                  <tr key={op.id}>
                    <td>
                      <strong>{op.label}</strong>
                      <div className="muted small">{op.description}</div>
                      {op.job ? (
                        <div className="small">
                          Running {op.job.done} / {op.job.total}
                          {op.job.current ? ` · ${op.job.current}` : ''}
                          {op.job.cancel_requested ? ' · stopping…' : ''}
                        </div>
                      ) : op.last ? (
                        <div className="small">
                          Last run {when(op.last.finished_at)}
                          {op.last.state === 'cancelled' ? ' (cancelled)' : ''}: {runSummary(op.last)}
                        </div>
                      ) : (
                        <div className="muted small">Never run</div>
                      )}
                      {report && (
                        <Link className="small" to={report.to}>
                          {report.label}
                        </Link>
                      )}
                      {op.id === 'pdf-check' && op.last && <PdfCheckReport />}
                    </td>
                    <td className="nowrap">
                      <label className="check">
                        <input
                          type="checkbox"
                          aria-label={`Run ${op.label} nightly`}
                          checked={nightly}
                          disabled={saving}
                          onChange={() =>
                            void saveSchedule(
                              data.hour,
                              nightly ? data.nightly.filter((i) => i !== op.id) : [...data.nightly, op.id],
                            )
                          }
                        />
                        Nightly
                      </label>
                    </td>
                    <td className="nowrap">
                      {op.job ? (
                        <button
                          type="button"
                          className="link"
                          disabled={op.job.cancel_requested}
                          onClick={() => op.job && void cancel(op.job.id)}
                        >
                          Cancel
                        </button>
                      ) : (
                        <button
                          type="button"
                          aria-label={`Run ${op.label}`}
                          className={op.destructive ? 'danger' : ''}
                          onClick={() => (op.destructive ? setConfirm(op) : void run(op))}
                        >
                          Run
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      {data.ops.some((o) => o.id === 'backup') && (
        <ServerBackups
          keep={data.keep_backups}
          onKeep={(n) => void saveSchedule(data.hour, data.nightly, n)}
          version={data.ops.find((o) => o.id === 'backup')?.last?.finished_at ?? null}
        />
      )}
      <ErrorText error={error} />
      <ConfirmDialog
        open={confirm !== null}
        title={`Run ${confirm?.label ?? ''} now?`}
        confirmLabel="Run"
        onConfirm={() => confirm && void run(confirm)}
        onCancel={() => setConfirm(null)}
      >
        <p>{confirm?.description}</p>
      </ConfirmDialog>
    </div>
  )
}
