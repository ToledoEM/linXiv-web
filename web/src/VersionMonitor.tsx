import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, idPath } from './api'
import { ErrorText } from './components'
import { MathText } from './tex'
import type { NewVersion } from './types'

/** arXiv version monitoring (desktop Settings → VersionMonitorSection). */
export default function VersionMonitor() {
  const [pending, setPending] = useState<NewVersion[] | null>(null)
  const [checking, setChecking] = useState(false)
  const [lastRun, setLastRun] = useState<{ checked: number; found: number } | null>(null)
  const [dismissing, setDismissing] = useState('')
  const [error, setError] = useState('')

  const load = useCallback(
    () =>
      api.newVersions().then(
        (r) => setPending(r.new_versions),
        (err: Error) => setError(err.message),
      ),
    [],
  )

  useEffect(() => {
    void load()
  }, [load])

  const check = async () => {
    setChecking(true)
    setError('')
    try {
      const r = await api.checkVersions()
      setLastRun({ checked: r.checked, found: r.new_versions.length })
      await load()
    } catch (err) {
      setError(`Version check failed (${(err as Error).message}). arXiv may be unreachable or rate-limiting; try again in a minute.`)
    } finally {
      setChecking(false)
    }
  }

  const dismiss = async (item: NewVersion) => {
    setDismissing(item.source_id)
    setError('')
    try {
      await api.ackVersion(item.source_id)
      await load()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setDismissing('')
    }
  }

  return (
    <div className="card settings-section">
      <h3>
        arXiv version monitoring
        {!!pending?.length && <span className="pill count-pill">{pending.length}</span>}
      </h3>
      <p className="muted small">
        Checks your saved arXiv papers for newer versions (stalest first, up to 20 per check) and stores anything new
        in the library.
      </p>
      <div className="actions">
        <button type="button" onClick={check} disabled={checking}>
          {checking ? 'Checking…' : 'Check for new versions'}
        </button>
        {lastRun && !checking && (
          <span className="muted small">
            Checked {lastRun.checked} paper{lastRun.checked === 1 ? '' : 's'},{' '}
            {lastRun.found === 0
              ? 'no new versions'
              : `found ${lastRun.found} new version${lastRun.found === 1 ? '' : 's'}`}
          </span>
        )}
      </div>
      <ErrorText error={error} />
      {pending === null ? (
        !error && <p className="muted small">Loading…</p>
      ) : pending.length === 0 ? (
        <p className="muted small">No unreviewed new versions.</p>
      ) : (
        <ul className="version-list">
          {pending.map((item) => (
            <li key={item.source_id}>
              <div>
                <Link to={`/paper/${idPath(item.source_id)}`}>
                  <MathText forceInline>{item.title}</MathText>
                </Link>
                <div className="muted small">New version available: v{item.version}</div>
              </div>
              <button
                type="button"
                className="link"
                disabled={dismissing === item.source_id}
                aria-label={`Dismiss ${item.title}`}
                onClick={() => dismiss(item)}
              >
                Dismiss
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
