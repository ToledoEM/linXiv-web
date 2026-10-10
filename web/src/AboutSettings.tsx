import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { api } from './api'
import { ErrorText } from './components'
import type { NcbiKeyStatus, SystemStatus, UpdateMode, UpdateStatus, UserSettings } from './types'

const MODES: { value: UpdateMode; label: string }[] = [
  { value: 'off', label: 'Off' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly (Recommended)' },
  { value: 'monthly', label: 'Monthly' },
]

const when = (ts: string) => new Date(ts).toLocaleString()

/** Disk sizes in GiB/TiB, as on Sonarr's status page. */
function formatSize(n: number): string {
  const gib = n / 1024 ** 3
  return gib >= 1024 ? `${(gib / 1024).toFixed(1)} TiB` : `${gib.toFixed(1)} GiB`
}

function UpdateLine({ u }: { u: UpdateStatus }) {
  if (u.update_available) {
    return (
      <p className="update-available">
        Version {u.latest} is available. Pull <span className="mono">{`${u.image}:${u.latest}`}</span>, then recreate
        the container (<span className="mono">docker compose pull &amp;&amp; docker compose up -d</span>).
      </p>
    )
  }
  if (u.latest && !u.error) return <p className="muted small">Up to date (latest release {u.latest}).</p>
  return null
}

/** Settings → About: version + release check, health, disk space (Sonarr-style status page). */
export default function AboutSettings({
  draft,
  set,
  token,
  envOverrides,
  busy,
  onRemoveToken,
  footer,
}: {
  draft: UserSettings
  set: <K extends keyof UserSettings>(key: K, value: UserSettings[K]) => void
  token: NcbiKeyStatus | null
  envOverrides: string[]
  busy: boolean
  onRemoveToken: () => void
  footer: ReactNode
}) {
  const [update, setUpdate] = useState<UpdateStatus | null>(null)
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState('')
  const [system, setSystem] = useState<SystemStatus | null>(null)
  const [systemError, setSystemError] = useState('')

  const loadSystem = useCallback(
    () =>
      api
        .systemStatus()
        .then((s) => {
          setSystem(s)
          setSystemError('')
        })
        .catch((err) => setSystemError((err as Error).message)),
    [],
  )

  useEffect(() => {
    api
      .updateStatus()
      .then(setUpdate)
      .catch((err) => setCheckError((err as Error).message))
    loadSystem()
  }, [loadSystem])

  const check = async () => {
    setChecking(true)
    setCheckError('')
    try {
      setUpdate(await api.checkUpdate())
      loadSystem()
    } catch (err) {
      setCheckError((err as Error).message)
    } finally {
      setChecking(false)
    }
  }

  return (
    <>
      <div className="card settings-section">
        <h3>About</h3>
        <div className="about-row">
          <div>
            <strong>linXiv-web</strong>
            <div className="muted small">Version {update?.current ?? '…'}</div>
          </div>
          <button type="button" onClick={check} disabled={checking}>
            {checking ? 'Checking…' : 'Check for updates'}
          </button>
        </div>
        {update && <UpdateLine u={update} />}
        {update?.error && <p className="error">Last check failed: {update.error}</p>}
        <ErrorText error={checkError} />
        {update?.checked_at && <p className="muted small">Last checked {when(update.checked_at)}.</p>}
        <p className="muted small">
          Web interface for linXiv. Open source under the Apache License 2.0.{' '}
          <a href="https://github.com/ToledoEM/linXiv-web" target="_blank" rel="noreferrer">
            Source on GitHub
          </a>
        </p>
        <div className="about-divider" />
        <label className="about-row">
          <span>
            <strong>Check automatically</strong>
            <span className="muted small block">
              Look for a new image release (ghcr.io tags) in the background on this schedule. Off by default.
            </span>
          </span>
          <select
            value={draft.web_update_check}
            onChange={(e) => set('web_update_check', e.target.value as UpdateMode)}
          >
            {MODES.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>GitHub token (only while the image is private)</span>
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={draft.GHCR_TOKEN}
            placeholder={token?.set ? 'Enter a new token to replace it' : 'Token with read:packages'}
            onChange={(e) => set('GHCR_TOKEN', e.target.value.trim())}
          />
          <span className="muted small">
            {token?.source === 'env' || envOverrides.includes('GHCR_TOKEN')
              ? `Set by the server environment (…${token?.last4 ?? ''}); it takes precedence.`
              : token?.set
                ? `Token saved (…${token.last4}).`
                : 'Not set: public images need none.'}
          </span>
        </label>
        {token?.source === 'settings' && (
          <div className="actions">
            <button type="button" className="link danger-link" disabled={busy} onClick={onRemoveToken}>
              Remove GitHub token
            </button>
          </div>
        )}
        {footer}
      </div>

      <div className="card settings-section">
        <h3>Health</h3>
        <ErrorText error={systemError} />
        {system &&
          (system.issues.length === 0 ? (
            <p>No issues with your configuration.</p>
          ) : (
            <ul className="health-list">
              {system.issues.map((i) => (
                <li key={i.message} className={`health-${i.level}`}>
                  <span className="pill">{i.level}</span> {i.message}
                </li>
              ))}
            </ul>
          ))}
      </div>

      <div className="card settings-section">
        <h3>Disk space</h3>
        {system && (
          <div className="table-wrap">
            <table className="disk-table">
              <thead>
                <tr>
                  <th>Location</th>
                  <th>Free space</th>
                  <th>Total space</th>
                  <th aria-label="Used" />
                </tr>
              </thead>
              <tbody>
                {system.disk.map((d) => (
                  <tr key={d.label}>
                    <td>
                      <span className="mono">{d.path}</span>
                      <span className="muted small block">{d.label}</span>
                    </td>
                    {d.error || d.total === undefined || d.free === undefined ? (
                      <td colSpan={3} className="error">
                        {d.error ?? 'unknown'}
                      </td>
                    ) : (
                      <>
                        <td className="nowrap">{formatSize(d.free)}</td>
                        <td className="nowrap">{formatSize(d.total)}</td>
                        <td className="disk-bar-cell">
                          <div
                            className="disk-bar"
                            role="meter"
                            aria-valuemin={0}
                            aria-valuemax={100}
                            aria-valuenow={Math.round(((d.total - d.free) / d.total) * 100)}
                            title={`${Math.round(((d.total - d.free) / d.total) * 100)}% used`}
                          >
                            <div style={{ width: `${((d.total - d.free) / d.total) * 100}%` }} />
                          </div>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
