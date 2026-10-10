import { useCallback, useEffect, useState } from 'react'
import { ACTIVITY_EXPORT_URL, api } from './api'
import { ErrorText } from './components'
import ConfirmDialog from './ConfirmDialog'
import type { ActivityEvent } from './types'

const PHRASE = 'delete activity log'
const LIMIT = 200

const when = (at: string) => new Date(at).toLocaleString()
const target = (t: Record<string, string>) => Object.values(t).join(', ')

/** Settings → Server & data → Activity: who changed what, when (no values recorded). */
export default function ActivityLog() {
  const [events, setEvents] = useState<ActivityEvent[] | null>(null)
  const [error, setError] = useState('')
  const [armed, setArmed] = useState(false)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setError('')
    try {
      setEvents((await api.activity(LIMIT)).events)
    } catch (err) {
      setError((err as Error).message)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const clear = async () => {
    setBusy(true)
    setError('')
    try {
      await api.clearActivity(PHRASE)
      setArmed(false)
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="card settings-section">
      <h3>Activity</h3>
      <p className="muted small">
        Every change made through the app: when, from which address, what route and on what. Request contents and
        setting values are never recorded (a Settings save lists only the names of the keys).
      </p>
      <div className="actions">
        <button type="button" onClick={() => void load()}>
          Refresh
        </button>
        <a className="button" href={ACTIVITY_EXPORT_URL} download>
          Download CSV
        </a>
      </div>
      <ErrorText error={error} />
      {events && events.length === 0 && <p className="muted small">No activity recorded yet.</p>}
      {events && events.length > 0 && (
        <div className="table-wrap">
          <table className="activity-table">
            <thead>
              <tr>
                <th>When</th>
                <th>From</th>
                <th>Action</th>
                <th>On</th>
                <th className="num">Status</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={`${e.at}-${i}`}>
                  <td className="small">{when(e.at)}</td>
                  <td className="mono small">{e.client}</td>
                  <td className="mono small">
                    {e.method} {e.route}
                    {e.fields && <div className="muted">{e.fields.join(', ')}</div>}
                  </td>
                  <td className="mono small">{target(e.target)}</td>
                  <td className={`num small ${e.status >= 400 ? 'st-error' : ''}`}>{e.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {events && events.length >= LIMIT && <p className="muted small">Showing the latest {LIMIT}; the CSV has all.</p>}
      <div className="actions">
        <button type="button" className="danger" disabled={busy} onClick={() => setArmed(true)}>
          Delete activity log
        </button>
      </div>
      <ConfirmDialog
        open={armed}
        busy={busy}
        title="Delete the activity log?"
        phrase={PHRASE}
        confirmLabel="Delete activity log"
        onConfirm={() => void clear()}
        onCancel={() => setArmed(false)}
      >
        <p>Every recorded change is removed. The deletion itself is recorded.</p>
      </ConfirmDialog>
    </div>
  )
}
